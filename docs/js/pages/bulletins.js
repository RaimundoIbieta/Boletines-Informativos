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
      <input id="title" value="${b?.title || ''}" placeholder="Boletín semanal minería Chile" />
      <label>Etiqueta corta</label>
      <input id="short_label" value="${b?.short_label || ''}" placeholder="Minería Chile" />
      <label>Audiencia</label>
      <input id="audience" value="${b?.audience || ''}" placeholder="gerentes y analistas" />
      <label>Enfoque</label>
      <textarea id="focus" placeholder="Qué debe cubrir el análisis...">${b?.focus || ''}</textarea>
      <label>Búsquedas web (una por línea: consulta | TEMA)</label>
      <textarea id="queries" placeholder="cobre Chile OR Codelco | MINERIA">${queriesToText(b?.queries)}</textarea>
      <label>Ejes de análisis (uno por línea)</label>
      <textarea id="axes">${(b?.analysis_axes || []).join('\n')}</textarea>
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
      <textarea id="emails" placeholder="tu@correo.cl">${recipients}</textarea>
      <label style="display:flex;gap:8px;align-items:center;text-transform:none;letter-spacing:0;font-size:.95rem">
        <input id="active" type="checkbox" ${(b?.active ?? true) ? 'checked' : ''} /> Activo
      </label>
      <div class="btn-row">
        <button class="btn" id="save">Guardar</button>
        <button class="btn btn-secondary" id="test">Probar envío</button>
        ${!isNew ? `<button class="btn btn-danger" id="del">Eliminar</button>` : ''}
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

  container.querySelector('#save').onclick = async () => {
    const err = container.querySelector('#err');
    const ok = container.querySelector('#ok');
    err.textContent = '';
    ok.textContent = '';
    try {
      const saved = await saveBulletin();
      ok.textContent = 'Guardado.';
      navigate(`#/boletin/${saved.id}`);
    } catch (e) {
      err.textContent = e.message;
    }
  };

  container.querySelector('#test').onclick = async () => {
    const err = container.querySelector('#err');
    const ok = container.querySelector('#ok');
    const btn = container.querySelector('#test');
    err.textContent = '';
    ok.textContent = '';
    btn.disabled = true;
    try {
      const saved = await saveBulletin({ requireEmails: true });
      const req = await requestTestSend(saved.id);
      ok.textContent = req.already
        ? 'Ya hay una prueba en cola. En unos minutos llegará el correo de prueba a los destinatarios.'
        : 'Prueba solicitada. En unos minutos (máx. ~10) se genera y envía el boletín de prueba a los correos guardados (periodo: lunes semana pasada → hoy).';
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
