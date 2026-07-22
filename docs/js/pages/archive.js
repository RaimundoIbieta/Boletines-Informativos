import { listPublicArchive, getUser } from '../auth.js';
import { navigate } from '../router.js';

export async function renderArchive(container) {
  const u = getUser();
  if (!u) return navigate('#/login');

  // Fallback: archivo estático local si no hay runs en DB
  let runs = [];
  try {
    runs = await listPublicArchive();
  } catch {
    runs = [];
  }

  let staticItems = [];
  try {
    const res = await fetch(`data/boletines.json?v=${Date.now()}`);
    if (res.ok) staticItems = await res.json();
  } catch {
    /* ignore */
  }

  container.innerHTML = `
    <h1 class="page-title">Archivo</h1>
    <p class="page-sub">PDFs generados. También puedes abrirlos en Drive cuando estén vinculados.</p>
    <div class="grid">
      ${
        runs.length
          ? runs
              .map(
                (r) => `
        <div class="card">
          <span class="chip">${r.status}</span>
          <p><strong>${r.periodo_inicio || ''} – ${r.periodo_fin || ''}</strong> · ${r.noticias || 0} noticias</p>
          <div class="btn-row">
            ${r.pdf_url ? `<a class="btn" href="${r.pdf_url}" target="_blank" rel="noopener">Ver PDF</a>` : ''}
            ${r.drive_url ? `<a class="btn btn-secondary" href="${r.drive_url}" target="_blank" rel="noopener">Drive</a>` : ''}
          </div>
        </div>`
              )
              .join('')
          : ''
      }
      ${staticItems
        .map(
          (item) => `
        <div class="card">
          <span class="chip">${item.theme_label || item.theme_id}</span>
          <h2 style="margin:8px 0;font-family:Fraunces,Georgia,serif;font-size:1.15rem">${item.theme_title}</h2>
          <p class="muted">Periodo ${item.periodo_inicio} – ${item.periodo_fin} · ${item.noticias} noticias</p>
          <div class="btn-row">
            ${item.pdf_local ? `<a class="btn" href="${item.pdf_local}" target="_blank">Ver PDF</a>` : ''}
            ${item.drive_view_link ? `<a class="btn btn-secondary" href="${item.drive_view_link}" target="_blank" rel="noopener">Abrir en Drive</a>` : ''}
          </div>
        </div>`
        )
        .join('')}
      ${!runs.length && !staticItems.length ? `<div class="card"><p>Sin boletines publicados aún.</p></div>` : ''}
    </div>
  `;
}
