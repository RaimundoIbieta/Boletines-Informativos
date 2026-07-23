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
    schedule_weekday: container.querySelector('#weekday').value,
    schedule_hour: Number(container.querySelector('#hour').value),
    schedule_minute: Number(container.querySelector('#minute').value),
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
          <p class="muted">${b.schedule_weekday} ${String(b.schedule_hour).padStart(2, '0')}:${String(b.schedule_minute).padStart(2, '0')} ·
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
      <div class="grid grid-3">
        <div>
          <label>Día</label>
          <select id="weekday">
            ${DAYS.map(
              ([k, lab]) =>
                `<option value="${k}" ${(b?.schedule_weekday || 'monday') === k ? 'selected' : ''}>${lab}</option>`
            ).join('')}
          </select>
        </div>
        <div>
          <label>Hora</label>
          <input id="hour" type="number" min="0" max="23" value="${b?.schedule_hour ?? 7}" />
        </div>
        <div>
          <label>Minuto</label>
          <input id="minute" type="number" min="0" max="59" value="${b?.schedule_minute ?? 30}" />
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
    if (isNew) saved = await createBulletin(payload);
    else saved = await updateBulletin(id, payload);
    await setRecipients(saved.id, emails);
    return saved;
  }

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
      const saved = await saveBulletin({ requireEmails: true });
      const req = await requestTestSend(saved.id);
      ok.textContent = req.already
        ? `Ya hay una prueba en cola (~${req.ageMin || 0} min). GitHub Actions la procesa cada ~10 min; revisa bandeja/spam de los destinatarios.`
        : 'Prueba solicitada. En unos minutos (máx. ~10–15) se genera y envía el boletín a los correos guardados. Revisa bandeja y spam.';
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
