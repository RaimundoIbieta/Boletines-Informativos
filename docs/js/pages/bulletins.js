import {
  getUser,
  hasActiveSubscription,
  isSuperAdmin,
  maxBulletins,
  listMyBulletins,
  createBulletin,
  updateBulletin,
  deleteBulletin,
  setRecipients,
  getBulletin,
  ensurePaeBulletin,
  requestTestSend,
} from '../auth.js';
import { navigate } from '../router.js';
import { isPaeBulletin } from '../paeTemplate.js';
import {
  suggestBulletinFields,
  formatQueries,
  formatAxes,
} from '../suggestFields.js';

const DAYS = [
  ['monday', 'Lunes'],
  ['tuesday', 'Martes'],
  ['wednesday', 'Miércoles'],
  ['thursday', 'Jueves'],
  ['friday', 'Viernes'],
  ['saturday', 'Sábado'],
  ['sunday', 'Domingo'],
];

function isoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Misma lógica que el motor: últimos N días incluyendo hoy, o semana previa lun–dom. */
function computePeriodBounds(mode, days, reference = new Date()) {
  const today = new Date(reference.getFullYear(), reference.getMonth(), reference.getDate());
  if (mode === 'calendar_semimonthly') {
    const start = new Date(today.getFullYear(), today.getMonth(), 1);
    const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    if (today.getDate() <= 15) {
      const endDay = today.getDate() === 15 ? 15 : today.getDate();
      const end = new Date(today.getFullYear(), today.getMonth(), endDay);
      return { start: isoDate(start), end: isoDate(end) };
    }
    const endDay = today.getDate() === lastDay ? lastDay : today.getDate();
    const end = new Date(today.getFullYear(), today.getMonth(), endDay);
    return { start: isoDate(start), end: isoDate(end) };
  }
  if (mode === 'previous_week') {
    const weekday = (today.getDay() + 6) % 7; // lunes=0
    const thisMonday = new Date(today);
    thisMonday.setDate(thisMonday.getDate() - weekday);
    const start = new Date(thisMonday);
    start.setDate(start.getDate() - 7);
    const end = new Date(thisMonday);
    end.setDate(end.getDate() - 1);
    return { start: isoDate(start), end: isoDate(end) };
  }
  const n = Math.max(1, Math.min(31, Number(days) || 7));
  const end = new Date(today);
  const start = new Date(end);
  start.setDate(start.getDate() - (n - 1));
  return { start: isoDate(start), end: isoDate(end) };
}

function parseQueries(text) {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      if (line.includes('|')) {
        const [q, topic] = line.split('|').map((x) => x.trim());
        return { q, topic: topic || 'GENERAL' };
      }
      return { q: line, topic: 'GENERAL' };
    });
}

function queriesToText(queries) {
  return (queries || []).map((x) => `${x.q || x[0]} | ${x.topic || x[1] || 'GENERAL'}`).join('\n');
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function readForm(container, { requireEmails = false } = {}) {
  const payload = {
    title: container.querySelector('#title').value.trim(),
    short_label: container.querySelector('#short_label').value.trim(),
    audience: container.querySelector('#audience').value.trim(),
    focus: container.querySelector('#focus').value.trim(),
    queries: parseQueries(container.querySelector('#queries').value),
    analysis_axes: container
      .querySelector('#axes')
      .value.split('\n')
      .map((x) => x.trim())
      .filter(Boolean),
    sections: container
      .querySelector('#sections')
      .value.split('\n')
      .map((x) => x.trim())
      .filter(Boolean),
    schedule_frequency: container.querySelector('#frequency').value,
    schedule_weekday: container.querySelector('#weekday').value,
    schedule_hour: Number(container.querySelector('#hour').value),
    schedule_minute: Number(container.querySelector('#minute').value),
    period_mode: container.querySelector('#period_mode').value,
    period_days: Number(container.querySelector('#period_days').value) || 7,
    output_format: container.querySelector('#output_format')?.value || 'standard',
    active: container.querySelector('#active').checked,
  };
  const emails = container
    .querySelector('#emails')
    .value.split('\n')
    .map((x) => x.trim())
    .filter(Boolean);
  if (!payload.title || !payload.short_label || !payload.focus || !payload.queries.length) {
    throw new Error('Completa título, etiqueta, enfoque y al menos una búsqueda.');
  }
  if (requireEmails && !emails.length) {
    throw new Error('Agrega al menos un correo destinatario para poder probar el envío.');
  }
  return { payload, emails };
}

export async function renderApp(container) {
  const u = getUser();
  if (!u) return navigate('#/login');
  if (!hasActiveSubscription() && !isSuperAdmin()) return navigate('#/plan');

  let list = await listMyBulletins();
  let importNote = '';
  if (isSuperAdmin() && !list.some(isPaeBulletin)) {
    try {
      await ensurePaeBulletin();
      list = await listMyBulletins();
      importNote = 'Se importó el boletín PAE (Programa de Alimentación Escolar) para que puedas editarlo y agregar correos.';
    } catch (e) {
      importNote = `No se pudo importar el PAE automáticamente: ${e.message}`;
    }
  }

  container.innerHTML = `
    <h1 class="page-title">Mis boletines</h1>
    <p class="page-sub">Plan: <strong>${u.plan || (isSuperAdmin() ? 'admin' : '—')}</strong> ·
      ${list.length}/${maxBulletins()} boletines</p>
    ${importNote ? `<p class="muted">${importNote}</p>` : ''}
    <div class="btn-row">
      <a class="btn" href="#/boletin/nuevo">Crear boletín</a>
      <a class="btn btn-secondary" href="#/archivo">Archivo / PDFs</a>
    </div>
    <div class="grid" style="margin-top:16px">
      ${
        list.length
          ? list
              .map(
                (b) => `
        <div class="card">
          <span class="chip">${b.short_label}</span>
          <h2 style="margin:8px 0;font-family:Fraunces,Georgia,serif;font-size:1.2rem">${b.title}</h2>
          <p class="muted">${b.schedule_frequency === 'semimonthly' ? 'Días 15 y fin de mes' : b.schedule_weekday} ${String(b.schedule_hour).padStart(2, '0')}:${String(b.schedule_minute).padStart(2, '0')} ·
            ${(b.bulletin_recipients || []).length} correo(s) · ${b.active ? 'activo' : 'pausado'}</p>
          <div class="btn-row">
            <a class="btn btn-secondary" href="#/boletin/${b.id}">Editar</a>
          </div>
        </div>`
              )
              .join('')
          : `<div class="card"><p>Aún no tienes boletines. Crea el primero.</p></div>`
      }
    </div>
  `;
}

export async function renderBulletinEditor(container, id) {
  const u = getUser();
  if (!u) return navigate('#/login');
  if (!hasActiveSubscription() && !isSuperAdmin()) return navigate('#/plan');

  const isNew = !id || id === 'nuevo';
  let b = null;
  if (!isNew) b = await getBulletin(id);

  const recipients = (b?.bulletin_recipients || []).map((r) => r.email).join('\n');
  const periodMode = b?.period_mode || 'last_n_days';
  const periodDays = b?.period_days ?? 7;
  const frequency = b?.schedule_frequency || 'weekly';
  const defaultPeriod = computePeriodBounds(periodMode, periodDays);

  container.innerHTML = `
    <h1 class="page-title">${isNew ? 'Nuevo boletín' : 'Editar boletín'}</h1>
    <p class="page-sub">Define temática, búsquedas, frecuencia y correos. Usa <strong>Probar envío</strong> para generar y mandar una prueba ahora (sin esperar el día programado).${
      !isNew && isPaeBulletin(b) ? ' Este es el boletín PAE.' : ''
    }</p>
    <div class="card">
      <label>Título</label>
      <input id="title" value="${escapeHtml(b?.title || '')}" placeholder="Boletín semanal minería Chile" />
      <label>Etiqueta corta</label>
      <input id="short_label" value="${escapeHtml(b?.short_label || '')}" placeholder="Minería Chile" />
      <label>Audiencia</label>
      <input id="audience" value="${escapeHtml(b?.audience || '')}" placeholder="gerentes y analistas" />
      <label>Enfoque</label>
      <textarea id="focus" placeholder="Qué debe cubrir el análisis...">${escapeHtml(b?.focus || '')}</textarea>
      <p class="muted" id="suggest-hint" style="margin:6px 0 12px">
        Al completar título/etiqueta/enfoque, las búsquedas y ejes se rellenan solos. Luego puedes editarlos, borrarlos o agregar líneas.
      </p>
      <div class="btn-row" style="margin:0 0 12px">
        <button type="button" class="btn btn-secondary" id="suggest-ai" style="padding:6px 10px;font-size:.8rem">Regenerar sugerencia</button>
      </div>
      <label>Búsquedas web (una por línea: consulta | TEMA)</label>
      <textarea id="queries" placeholder="cobre Chile OR Codelco | MINERIA">${escapeHtml(queriesToText(b?.queries))}</textarea>
      <label>Ejes de análisis (uno por línea)</label>
      <textarea id="axes">${escapeHtml((b?.analysis_axes || []).join('\n'))}</textarea>
      <label>Secciones del informe (una por línea)</label>
      <textarea id="sections" placeholder="Economía&#10;Social&#10;Política&#10;Nacional&#10;Internacional">${escapeHtml((b?.sections || []).join('\n'))}</textarea>
      <p class="muted" style="margin:4px 0 10px">
        En formato <strong>Panorama</strong> estas secciones son libres: puedes usar Deportes, Misceláneo, Cine y teatro, Cultura, etc.
        Cada línea debe coincidir con el TEMA de las búsquedas (ej. <code>consulta | DEPORTES</code>).
        Si usas <strong>Internacional</strong>, debe significar hechos del mundo que puedan afectar a Chile, no “Chile en el extranjero”.
      </p>
      <div class="grid grid-3">
        <div>
          <label>Frecuencia</label>
          <select id="frequency">
            <option value="weekly" ${frequency === 'weekly' ? 'selected' : ''}>Semanal</option>
            <option value="semimonthly" ${frequency === 'semimonthly' ? 'selected' : ''}>Días 15 y último del mes</option>
          </select>
        </div>
        <div id="weekday-wrap" style="${frequency === 'semimonthly' ? 'display:none' : ''}">
          <label>Día de envío semanal</label>
          <select id="weekday">
            ${DAYS.map(
              ([k, lab]) =>
                `<option value="${k}" ${(b?.schedule_weekday || 'monday') === k ? 'selected' : ''}>${lab}</option>`
            ).join('')}
          </select>
        </div>
      </div>
      <div class="grid grid-3">
        <div>
          <label>Hora</label>
          <input id="hour" type="number" min="0" max="23" value="${b?.schedule_hour ?? 7}" />
        </div>
        <div>
          <label>Minuto</label>
          <input id="minute" type="number" min="0" max="59" value="${b?.schedule_minute ?? 30}" />
        </div>
      </div>
      <label style="margin-top:12px">Periodo de selección de noticias</label>
      <p class="muted" style="margin:4px 0 10px">Define qué rango de fechas se busca en cada envío programado. En prueba puedes ajustar las fechas abajo.</p>
      <div class="grid grid-3">
        <div>
          <label>Modo</label>
          <select id="period_mode">
            <option value="last_n_days" ${periodMode === 'last_n_days' ? 'selected' : ''}>Últimos N días (incluye el día de envío)</option>
            <option value="previous_week" ${periodMode === 'previous_week' ? 'selected' : ''}>Semana previa cerrada (lun–dom)</option>
            <option value="calendar_semimonthly" ${periodMode === 'calendar_semimonthly' ? 'selected' : ''}>Calendario quincenal (15 y fin de mes)</option>
          </select>
        </div>
        <div id="period-days-wrap" style="${periodMode !== 'last_n_days' ? 'display:none' : ''}">
          <label>Días (N)</label>
          <input id="period_days" type="number" min="1" max="31" value="${periodDays}" />
        </div>
        <div></div>
      </div>
      <p class="muted" style="margin:4px 0 10px">
        Con <strong>Últimos N días</strong> el boletín del viernes 18:30 incluye lo que pasó ese mismo viernes.
        La <strong>semana previa cerrada</strong> termina el domingo anterior, así que no cubre el día de envío.
        El <strong>calendario quincenal</strong> cubre los días 1–15 el día 15, y el mes completo el último día del mes.
      </p>
      <label style="margin-top:12px">Formato del informe</label>
      <select id="output_format">
        <option value="standard" ${(b?.output_format || 'standard') === 'standard' ? 'selected' : ''}>Estándar (comentario, riesgos y oportunidades por noticia)</option>
        <option value="panorama_sectional" ${b?.output_format === 'panorama_sectional' ? 'selected' : ''}>Panorama por secciones (resumen corto + síntesis de sección + conclusión)</option>
      </select>
      <p class="muted" style="margin:4px 0 10px">El formato panorama usa las secciones que definas arriba (no están un set fijo). El estándar ignora ese layout y mantiene el análisis por noticia.</p>
      <div class="grid grid-3" style="margin-top:8px">
        <div>
          <label>Desde (prueba)</label>
          <input id="period_start" type="date" value="${defaultPeriod.start}" />
        </div>
        <div>
          <label>Hasta (prueba)</label>
          <input id="period_end" type="date" value="${defaultPeriod.end}" />
        </div>
        <div style="display:flex;align-items:flex-end">
          <button type="button" class="btn btn-secondary" id="period-reset" style="padding:8px 10px;font-size:.8rem">Usar modo</button>
        </div>
      </div>
      <label>Correos destinatarios (uno por línea)</label>
      <textarea id="emails" placeholder="tu@correo.cl">${escapeHtml(recipients)}</textarea>
      <label style="display:flex;gap:8px;align-items:center;text-transform:none;letter-spacing:0;font-size:.95rem">
        <input id="active" type="checkbox" ${(b?.active ?? true) ? 'checked' : ''} /> Activo
      </label>
      <div class="btn-row">
        <button type="button" class="btn" id="save">Guardar</button>
        <button type="button" class="btn btn-secondary" id="test">Probar envío</button>
        ${!isNew ? `<button type="button" class="btn btn-danger" id="del">Eliminar</button>` : ''}
        <a class="btn btn-secondary" href="#/app">Volver</a>
      </div>
      <p class="error" id="err"></p>
      <p class="muted" id="ok"></p>
    </div>
  `;

  async function saveBulletin({ requireEmails = false } = {}) {
    const { payload, emails } = readForm(container, { requireEmails });
    let saved;
    try {
      if (isNew) saved = await createBulletin(payload);
      else saved = await updateBulletin(id, payload);
    } catch (e) {
      const msg = e.message || String(e);
      if (/period_mode|period_days|schedule_frequency|sections|output_format|schema cache|column/i.test(msg)) {
        throw new Error(
          'Falta actualizar Supabase. Ejecuta supabase/panorama_output_format.sql (y semimonthly_bulletins.sql si aplica) y vuelve a guardar.'
        );
      }
      throw e;
    }
    await setRecipients(saved.id, emails);
    return saved;
  }

  function syncPeriodDatesFromMode() {
    const mode = container.querySelector('#period_mode').value;
    const days = container.querySelector('#period_days').value;
    const wrap = container.querySelector('#period-days-wrap');
    if (wrap) wrap.style.display = mode === 'last_n_days' ? '' : 'none';
    const bounds = computePeriodBounds(mode, days);
    container.querySelector('#period_start').value = bounds.start;
    container.querySelector('#period_end').value = bounds.end;
  }

  container.querySelector('#period_mode').onchange = syncPeriodDatesFromMode;
  container.querySelector('#period_days').oninput = () => {
    if (container.querySelector('#period_mode').value === 'last_n_days') syncPeriodDatesFromMode();
  };
  container.querySelector('#period-reset').onclick = syncPeriodDatesFromMode;

  function syncFrequency() {
    const semimonthly = container.querySelector('#frequency').value === 'semimonthly';
    container.querySelector('#weekday-wrap').style.display = semimonthly ? 'none' : '';
    if (semimonthly) {
      container.querySelector('#period_mode').value = 'calendar_semimonthly';
      syncPeriodDatesFromMode();
    }
  }
  container.querySelector('#frequency').onchange = syncFrequency;

  const qEl = container.querySelector('#queries');
  const aEl = container.querySelector('#axes');
  const ok = container.querySelector('#ok');
  const err = container.querySelector('#err');
  const hint = container.querySelector('#suggest-hint');
  let userEditedFields = false;
  let lastSuggestKey = '';
  let suggestTimer = null;
  let suggesting = false;

  qEl.addEventListener('input', () => {
    userEditedFields = true;
  });
  aEl.addEventListener('input', () => {
    userEditedFields = true;
  });

  async function runSuggest({ force = false } = {}) {
    const input = {
      title: container.querySelector('#title').value.trim(),
      short_label: container.querySelector('#short_label').value.trim(),
      audience: container.querySelector('#audience').value.trim(),
      focus: container.querySelector('#focus').value.trim(),
    };
    if (!input.title && !input.short_label && !input.focus) return;
    // Esperar al menos título o etiqueta + algo de contexto
    if (!(input.title || input.short_label)) return;

    const key = JSON.stringify(input);
    if (!force && key === lastSuggestKey) return;
    if (!force && userEditedFields && (qEl.value.trim() || aEl.value.trim())) return;
    if (!force && qEl.value.trim() && aEl.value.trim()) return;

    if (suggesting) return;
    suggesting = true;
    const btn = container.querySelector('#suggest-ai');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Generando…';
    }
    if (hint) hint.style.opacity = '0.7';
    err.textContent = '';
    try {
      const suggestion = await suggestBulletinFields(input);
      qEl.value = formatQueries(suggestion.queries);
      aEl.value = formatAxes(suggestion.analysis_axes);
      lastSuggestKey = key;
      userEditedFields = false;
      ok.textContent =
        suggestion.source === 'gemini'
          ? 'Búsquedas y ejes rellenados con IA. Puedes editarlos libremente.'
          : 'Búsquedas y ejes rellenados automáticamente. Puedes editarlos libremente.';
    } catch (e) {
      if (force) err.textContent = e.message || String(e);
    } finally {
      suggesting = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Regenerar';
      }
      if (hint) hint.style.opacity = '1';
    }
  }

  function scheduleSuggest() {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(() => runSuggest({ force: false }), 650);
  }

  for (const sel of ['#title', '#short_label', '#audience', '#focus']) {
    const el = container.querySelector(sel);
    el.addEventListener('input', scheduleSuggest);
    el.addEventListener('blur', () => runSuggest({ force: false }));
  }

  container.querySelector('#suggest-ai').onclick = () => runSuggest({ force: true });

  container.querySelector('#save').onclick = async () => {
    const btn = container.querySelector('#save');
    err.textContent = '';
    ok.textContent = '';
    btn.disabled = true;
    const prev = btn.textContent;
    btn.textContent = 'Guardando…';
    try {
      const saved = await saveBulletin();
      ok.textContent = 'Guardado correctamente.';
      if (isNew) navigate(`#/boletin/${saved.id}`);
    } catch (e) {
      err.textContent = e.message || String(e);
    } finally {
      btn.disabled = false;
      btn.textContent = prev;
    }
  };

  container.querySelector('#test').onclick = async () => {
    const btn = container.querySelector('#test');
    err.textContent = '';
    ok.textContent = '';
    btn.disabled = true;
    try {
      const start = container.querySelector('#period_start').value;
      const end = container.querySelector('#period_end').value;
      if (!start || !end) throw new Error('Indica el periodo Desde / Hasta para la prueba.');
      if (end < start) throw new Error('La fecha Hasta no puede ser anterior a Desde.');
      const saved = await saveBulletin({ requireEmails: true });
      const req = await requestTestSend(saved.id, {
        periodo_inicio: start,
        periodo_fin: end,
      });
      if (req.updatedPeriod) {
        ok.textContent = `Ya había una prueba en cola (~${req.ageMin || 0} min) con otro rango; se actualizó a ${start} → ${end}. GitHub Actions la procesa cada ~10 min.`;
      } else if (req.already) {
        ok.textContent = `Ya hay una prueba en cola (~${req.ageMin || 0} min) con el mismo rango ${start} → ${end}. GitHub Actions la procesa cada ~10 min; revisa bandeja/spam.`;
      } else {
        ok.textContent = `Prueba solicitada (${start} → ${end}). En unos minutos (máx. ~10–15) se genera y envía el boletín. Revisa bandeja y spam.`;
      }
      if (isNew) navigate(`#/boletin/${saved.id}`);
    } catch (e) {
      err.textContent = e.message;
    } finally {
      btn.disabled = false;
    }
  };

  const del = container.querySelector('#del');
  if (del) {
    del.onclick = async () => {
      if (!confirm('¿Eliminar este boletín?')) return;
      await deleteBulletin(id);
      navigate('#/app');
    };
  }
}
