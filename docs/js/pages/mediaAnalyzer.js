import { client, getUser, isSuperAdmin } from '../auth.js';
import { navigate } from '../router.js';

const REGIONS = [
  ['15', 'Arica y Parinacota'],
  ['01', 'Tarapacá'],
  ['02', 'Antofagasta'],
  ['03', 'Atacama'],
  ['04', 'Coquimbo'],
  ['05', 'Valparaíso'],
  ['13', 'Metropolitana'],
  ['06', "O'Higgins"],
  ['07', 'Maule'],
  ['16', 'Ñuble'],
  ['08', 'Biobío'],
  ['09', 'La Araucanía'],
  ['14', 'Los Ríos'],
  ['10', 'Los Lagos'],
  ['11', 'Aysén'],
  ['12', 'Magallanes'],
];

const SOURCES = [
  ['news', 'Medios digitales', false],
  ['youtube', 'YouTube', false],
  ['reddit', 'Reddit', false],
  ['bluesky', 'Bluesky', false],
  ['mastodon', 'Mastodon', false],
  ['x', 'X (Twitter)', true],
  ['instagram', 'Instagram', true],
  ['facebook', 'Facebook', true],
  ['tiktok', 'TikTok', true],
];

const COVERAGE_METHODS = {
  public_api: 'API pública',
  public_search: 'Búsqueda pública',
  media_citation: 'Citado por medios',
  user_supplied: 'Aportado por ti',
  unavailable: 'No disponible',
};

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function isoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function defaultPeriod() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  return { start: isoDate(start), end: isoDate(end) };
}

function statusLabel(status) {
  const map = {
    pending: 'En cola',
    running: 'Procesando',
    validating: 'Validando',
    collecting: 'Recolectando',
    extracting: 'Extrayendo',
    analyzing: 'Analizando',
    rendering: 'Generando informe',
    completed: 'Listo',
    partial: 'Parcial',
    failed: 'Falló',
    cancelled: 'Cancelado',
  };
  return map[status] || status;
}

function guardAdmin() {
  const u = getUser();
  if (!u) {
    navigate('#/login');
    return null;
  }
  if (!isSuperAdmin()) {
    return false;
  }
  return u;
}

export async function renderMediaAnalyzerList(container) {
  const u = guardAdmin();
  if (u === null) return;
  if (u === false) {
    container.innerHTML = `<div class="card"><p class="error">Piloto: solo el administrador puede usar el Analizador de Medios.</p></div>`;
    return;
  }

  const { data, error } = await client()
    .from('media_analysis_requests')
    .select('id,topic,territory_label,period_start,period_end,status,progress,current_stage,created_at,error')
    .order('created_at', { ascending: false })
    .limit(40);

  if (error) {
    container.innerHTML = `<div class="card"><p class="error">${escapeHtml(error.message)}</p>
      <p class="muted">Si falta la tabla, ejecuta <code>supabase/media_analysis.sql</code>.</p></div>`;
    return;
  }

  const rows = data || [];
  container.innerHTML = `
    <h1 class="page-title">Analizador de Medios</h1>
    <p class="page-sub">Radiografías bajo demanda por tema, territorio y periodo. Piloto exclusivo del administrador.</p>
    <div class="btn-row">
      <a class="btn" href="#/analizador/nuevo">Nuevo análisis</a>
      <a class="btn btn-secondary" href="#/app">Volver a boletines</a>
    </div>
    <div class="card" style="margin-top:16px">
      ${
        rows.length
          ? `<table class="table"><thead><tr>
              <th>Tema</th><th>Territorio</th><th>Periodo</th><th>Estado</th><th></th>
            </tr></thead><tbody>
            ${rows
              .map(
                (r) => `<tr>
              <td>${escapeHtml(r.topic)}</td>
              <td>${escapeHtml(r.territory_label || 'Chile')}</td>
              <td>${escapeHtml(r.period_start)} → ${escapeHtml(r.period_end)}</td>
              <td><span class="chip">${escapeHtml(statusLabel(r.status))}</span>
                ${r.progress != null ? `<span class="muted"> ${r.progress}%</span>` : ''}</td>
              <td><a class="btn btn-secondary" href="#/analizador/${r.id}">Ver</a></td>
            </tr>`
              )
              .join('')}
            </tbody></table>`
          : `<p class="muted">Aún no hay análisis. Crea el primero.</p>`
      }
    </div>
  `;
}

export async function renderMediaAnalyzerNew(container) {
  const u = guardAdmin();
  if (u === null) return;
  if (u === false) {
    container.innerHTML = `<div class="card"><p class="error">Piloto: solo el administrador.</p></div>`;
    return;
  }
  const period = defaultPeriod();
  container.innerHTML = `
    <div class="composer">
      <header class="composer-head">
        <span class="chip">Analizador de medios</span>
        <h1 class="page-title">Nuevo análisis</h1>
        <p class="page-sub">Una radiografía de lo que dicen los medios y las redes sobre el tema
        que definas, en el territorio y periodo que elijas.</p>
      </header>

      <div class="composer-body">
        <div class="composer-main">
          <section class="step">
            <div class="step-head">
              <span class="step-num">1</span>
              <div>
                <h2 class="step-title">Qué quieres analizar</h2>
                <p class="step-sub">El tema guía la búsqueda; los actores reciben medición de tono.</p>
              </div>
            </div>
            <div class="field">
              <label for="topic">Tema</label>
              <input id="topic" class="input-lg" placeholder="Ej. quién será el próximo presidente de Chile" />
            </div>
            <div class="field-row">
              <div class="field">
                <label for="actors">Actores a medir</label>
                <textarea id="actors" rows="3" placeholder="José Antonio Kast&#10;candidato A&#10;candidato B"></textarea>
                <p class="hint">Uno por línea. Se mide el tono dirigido a cada uno.</p>
              </div>
              <div class="field">
                <label for="rivals">Comparar con</label>
                <textarea id="rivals" rows="3" placeholder="Lionel Messi&#10;Neymar"></textarea>
                <p class="hint">Uno por línea. Mide quién gana cuando la gente compara
                («es mejor que», «prefiero a»).</p>
              </div>
            </div>
          </section>

          <section class="step">
            <div class="step-head">
              <span class="step-num">2</span>
              <div>
                <h2 class="step-title">Dónde y cuándo</h2>
                <p class="step-sub">Las menciones desde el extranjero se clasifican, no se descartan.</p>
              </div>
            </div>
            <div class="field-row">
              <div class="field">
                <label for="territory_level">Nivel territorial</label>
                <select id="territory_level">
                  <option value="national">Nacional</option>
                  <option value="regional">Regional</option>
                  <option value="communal">Comunal</option>
                </select>
              </div>
              <div class="field">
                <label for="territory_label">Etiqueta territorial</label>
                <input id="territory_label" value="Chile" />
              </div>
            </div>
            <div class="field-row" id="geo-row" style="display:none">
              <div class="field" id="region-wrap" style="display:none">
                <label for="region_code">Región</label>
                <select id="region_code">
                  <option value="">—</option>
                  ${REGIONS.map(([c, n]) => `<option value="${c}">${escapeHtml(n)}</option>`).join('')}
                </select>
              </div>
              <div class="field" id="commune-wrap" style="display:none">
                <label for="commune_code">Comuna (código o nombre)</label>
                <input id="commune_code" placeholder="Ej. 13101 o Santiago" />
              </div>
            </div>
            <div class="field">
              <label>Periodo</label>
              <div class="preset-row">
                ${[
                  [7, '7 días'],
                  [30, '30 días'],
                  [90, '90 días'],
                  [365, '1 año'],
                ]
                  .map(
                    ([days, text]) =>
                      `<button type="button" class="preset" data-days="${days}">${text}</button>`
                  )
                  .join('')}
              </div>
            </div>
            <div class="field-row">
              <div class="field">
                <label for="period_start">Desde</label>
                <input id="period_start" type="date" value="${period.start}" />
              </div>
              <div class="field">
                <label for="period_end">Hasta</label>
                <input id="period_end" type="date" value="${period.end}" />
              </div>
            </div>
            <p class="hint">Máximo 2 años. Las redes gratuitas tienen cobertura histórica parcial.</p>
          </section>

          <section class="step">
            <div class="step-head">
              <span class="step-num">3</span>
              <div>
                <h2 class="step-title">Fuentes</h2>
                <p class="step-sub">Toca para activar o desactivar cada una.</p>
              </div>
              <button type="button" class="link-btn" id="toggle-sources">Quitar todas</button>
            </div>
            <div class="source-grid">
              ${SOURCES.map(
                ([value, label, restricted]) =>
                  `<label class="source-chip">
                    <input type="checkbox" class="src" value="${value}" checked />
                    <span>${escapeHtml(label)}${restricted ? '<span class="source-mark">*</span>' : ''}</span>
                  </label>`
              ).join('')}
            </div>
            <p class="hint">* X, Instagram, Facebook y TikTok no tienen API abierta ni buscador que
            permita rastrearlas. Se cubren con las publicaciones que los medios citan e incrustan, y
            con los enlaces o archivos que aportes. No es una muestra completa de esas redes.</p>
          </section>

          <section class="step">
            <div class="step-head">
              <span class="step-num">4</span>
              <div>
                <h2 class="step-title">Ajustes opcionales</h2>
                <p class="step-sub">Solo si necesitas acotar la búsqueda o sumar material propio.</p>
              </div>
            </div>
            <details class="form-details">
              <summary>Afinar con términos</summary>
              <div class="field-row">
                <div class="field">
                  <label for="include">Incluir términos</label>
                  <textarea id="include" rows="3" placeholder="elección&#10;encuesta"></textarea>
                </div>
                <div class="field">
                  <label for="exclude">Excluir términos</label>
                  <textarea id="exclude" rows="3"></textarea>
                </div>
              </div>
              <p class="hint">Uno por línea.</p>
            </details>
            <details class="form-details">
              <summary>Aportar material propio</summary>
              <div class="field">
                <label for="x_accounts">Cuentas públicas de X a leer</label>
                <textarea id="x_accounts" rows="3" placeholder="@PresidenteKast&#10;@Cristiano&#10;https://x.com/usuario"></textarea>
                <p class="hint">Una por línea. Lee sus publicaciones públicas sin seguirlas ni
                iniciar sesión. X no permite buscar por tema sin sesión, así que para saber quién
                habla de alguien hay que indicar las cuentas o aportar enlaces.</p>
              </div>
              <div class="field">
                <label for="urls">URLs de publicaciones o notas</label>
                <textarea id="urls" rows="3" placeholder="https://x.com/usuario/status/123&#10;https://www.instagram.com/p/..."></textarea>
              </div>
              <div class="field">
                <label for="files">Archivos (txt, md, csv, json, html, pdf)</label>
                <input id="files" type="file" multiple accept=".txt,.md,.csv,.json,.html,.htm,.pdf,text/plain,application/pdf" />
              </div>
            </details>
          </section>
        </div>

        <aside class="composer-side">
          <div class="summary">
            <h2 class="summary-title">Resumen</h2>
            <dl class="summary-list">
              <div><dt>Tema</dt><dd id="sum-topic" class="summary-empty">Sin definir</dd></div>
              <div><dt>Territorio</dt><dd id="sum-territory">Chile</dd></div>
              <div><dt>Periodo</dt><dd id="sum-period">—</dd></div>
              <div><dt>Actores</dt><dd id="sum-actors" class="summary-empty">Ninguno</dd></div>
              <div><dt>Fuentes</dt><dd id="sum-sources">—</dd></div>
            </dl>
            <button type="button" class="btn btn-block" id="submit">Generar radiografía</button>
            <a class="btn btn-secondary btn-block" href="#/analizador">Cancelar</a>
            <p class="error" id="err"></p>
            <p class="muted" id="ok"></p>
            <p class="hint">El procesamiento corre en segundo plano y suele tardar unos minutos.</p>
          </div>
        </aside>
      </div>
    </div>
  `;

  const levelEl = container.querySelector('#territory_level');
  const startEl = container.querySelector('#period_start');
  const endEl = container.querySelector('#period_end');

  const setSummary = (id, text, empty) => {
    const el = container.querySelector(id);
    el.textContent = text;
    el.classList.toggle('summary-empty', Boolean(empty));
  };

  const syncSummary = () => {
    const topic = container.querySelector('#topic').value.trim();
    setSummary('#sum-topic', topic || 'Sin definir', !topic);
    setSummary('#sum-territory', container.querySelector('#territory_label').value.trim() || 'Chile');

    const days =
      startEl.value && endEl.value
        ? Math.round((new Date(endEl.value) - new Date(startEl.value)) / 86400000) + 1
        : 0;
    setSummary('#sum-period', days > 0 ? `${days} días` : '—', days <= 0);

    const actors = container
      .querySelector('#actors')
      .value.split('\n')
      .map((x) => x.trim())
      .filter(Boolean);
    setSummary('#sum-actors', actors.length ? actors.join(', ') : 'Ninguno', !actors.length);

    const checked = container.querySelectorAll('.src:checked').length;
    setSummary(
      '#sum-sources',
      checked ? `${checked} de ${SOURCES.length}` : 'Ninguna',
      !checked
    );
    container.querySelector('#toggle-sources').textContent =
      checked === SOURCES.length ? 'Quitar todas' : 'Activar todas';
  };

  const syncTerritory = () => {
    const level = levelEl.value;
    const needsRegion = level === 'regional' || level === 'communal';
    container.querySelector('#geo-row').style.display = needsRegion ? '' : 'none';
    container.querySelector('#region-wrap').style.display = needsRegion ? '' : 'none';
    container.querySelector('#commune-wrap').style.display = level === 'communal' ? '' : 'none';
    if (level === 'national') container.querySelector('#territory_label').value = 'Chile';
    syncSummary();
  };
  levelEl.onchange = syncTerritory;
  container.querySelector('#region_code').onchange = () => {
    const opt = container.querySelector('#region_code').selectedOptions[0];
    if (opt?.value) container.querySelector('#territory_label').value = opt.textContent;
    syncSummary();
  };

  container.querySelectorAll('.preset').forEach((btn) => {
    btn.onclick = () => {
      const days = Number(btn.dataset.days);
      const end = new Date();
      const start = new Date(end);
      start.setDate(start.getDate() - (days - 1));
      startEl.value = isoDate(start);
      endEl.value = isoDate(end);
      syncSummary();
    };
  });

  container.querySelector('#toggle-sources').onclick = () => {
    const boxes = [...container.querySelectorAll('.src')];
    const activate = boxes.some((b) => !b.checked);
    boxes.forEach((b) => {
      b.checked = activate;
    });
    syncSummary();
  };

  container.addEventListener('input', syncSummary);
  container.addEventListener('change', syncSummary);
  syncSummary();

  container.querySelector('#submit').onclick = async () => {
    const err = container.querySelector('#err');
    const ok = container.querySelector('#ok');
    const btn = container.querySelector('#submit');
    err.textContent = '';
    ok.textContent = '';
    btn.disabled = true;
    try {
      const topic = container.querySelector('#topic').value.trim();
      const period_start = container.querySelector('#period_start').value;
      const period_end = container.querySelector('#period_end').value;
      if (!topic) throw new Error('Indica el tema.');
      if (!period_start || !period_end) throw new Error('Indica el periodo.');
      if (period_end < period_start) throw new Error('Hasta no puede ser anterior a Desde.');
      const days =
        (new Date(period_end) - new Date(period_start)) / (1000 * 60 * 60 * 24);
      if (days > 730) throw new Error('Periodo máximo: 2 años.');
      const territory_level = levelEl.value;
      const region_code = container.querySelector('#region_code').value || null;
      const commune_code = container.querySelector('#commune_code').value.trim() || null;
      if (territory_level !== 'national' && !region_code) {
        throw new Error('Selecciona una región.');
      }
      if (territory_level === 'communal' && !commune_code) {
        throw new Error('Indica la comuna.');
      }
      const actors = container
        .querySelector('#actors')
        .value.split('\n')
        .map((x) => x.trim())
        .filter(Boolean);
      const include_terms = container
        .querySelector('#include')
        .value.split('\n')
        .map((x) => x.trim())
        .filter(Boolean);
      const exclude_terms = container
        .querySelector('#exclude')
        .value.split('\n')
        .map((x) => x.trim())
        .filter(Boolean);
      const enabled_sources = [...container.querySelectorAll('.src:checked')].map((x) => x.value);
      const xAccounts = container
        .querySelector('#x_accounts')
        .value.split('\n')
        .map((x) => x.trim().replace(/^@/, ''))
        .filter(Boolean)
        .slice(0, 12);
      const rivals = container
        .querySelector('#rivals')
        .value.split('\n')
        .map((x) => x.trim())
        .filter(Boolean)
        .slice(0, 4);
      const urls = container
        .querySelector('#urls')
        .value.split('\n')
        .map((x) => x.trim())
        .filter(Boolean)
        .filter((u) => /^https?:\/\//i.test(u));

      ok.textContent = 'Creando solicitud…';
      const { data: rid, error: rpcErr } = await client().rpc('create_media_analysis_request', {
        p_topic: topic,
        p_period_start: period_start,
        p_period_end: period_end,
        p_territory_level: territory_level,
        p_region_code: region_code,
        p_commune_code: commune_code,
        p_territory_label: container.querySelector('#territory_label').value.trim() || 'Chile',
        p_actors: actors,
        p_include_terms: include_terms,
        p_exclude_terms: exclude_terms,
        p_enabled_sources: enabled_sources,
        p_urls: urls,
        p_configuration: {
          default_window_days: 30,
          max_years: 2,
          x_accounts: xAccounts,
          rivals,
        },
      });
      if (rpcErr) {
        if (/media_analysis|schema cache|does not exist|function/i.test(rpcErr.message)) {
          throw new Error('Falta ejecutar supabase/media_analysis.sql en Supabase.');
        }
        throw new Error(rpcErr.message);
      }

      // Subir archivos a Storage si hay
      const files = container.querySelector('#files').files;
      if (files?.length) {
        for (const file of files) {
          if (file.size > 5_000_000) throw new Error(`Archivo demasiado grande: ${file.name}`);
          const path = `${u.id}/${rid}/${crypto.randomUUID()}_${file.name}`;
          const { error: upErr } = await client()
            .storage.from('media-analysis-inputs')
            .upload(path, file, { upsert: false });
          if (upErr) throw new Error(upErr.message);
          const { error: insErr } = await client().from('media_analysis_inputs').insert({
            request_id: rid,
            user_id: u.id,
            kind: 'file',
            storage_path: path,
            file_name: file.name,
            mime_type: file.type || null,
            size_bytes: file.size,
            status: 'pending',
          });
          if (insErr) throw new Error(insErr.message);
        }
      }

      // Disparar worker (Edge Function; si falla, el cron lo recoge)
      try {
        await client().functions.invoke('queue-media-analysis', { body: { request_id: rid } });
      } catch {
        // El workflow cron de respaldo procesará la cola
      }

      ok.textContent = 'Análisis encolado. Suele tardar unos minutos.';
      navigate(`#/analizador/${rid}`);
    } catch (e) {
      err.textContent = e.message || String(e);
    } finally {
      btn.disabled = false;
    }
  };
}

export async function renderMediaAnalyzerDetail(container, id) {
  const u = guardAdmin();
  if (u === null) return;
  if (u === false) {
    container.innerHTML = `<div class="card"><p class="error">Piloto: solo el administrador.</p></div>`;
    return;
  }

  const sb = client();
  const { data: req, error } = await sb
    .from('media_analysis_requests')
    .select('*')
    .eq('id', id)
    .maybeSingle();
  if (error || !req) {
    container.innerHTML = `<div class="card"><p class="error">${escapeHtml(error?.message || 'No encontrado')}</p>
      <a class="btn btn-secondary" href="#/analizador">Volver</a></div>`;
    return;
  }

  const { data: result } = await sb
    .from('media_analysis_results')
    .select('*')
    .eq('request_id', id)
    .maybeSingle();
  const { data: docs } = await sb
    .from('media_analysis_documents')
    .select('id,title,publisher,url,source_type,published_at,excerpt')
    .eq('request_id', id)
    .eq('included', true)
    .order('published_at', { ascending: false })
    .limit(40);
  const { data: artifacts } = await sb
    .from('media_analysis_artifacts')
    .select('*')
    .eq('request_id', id);

  const actors = result?.actors || [];
  const findings = result?.findings || [];
  const warnings = result?.warnings || [];
  const coverage = result?.coverage_metrics || {};
  const sentiment = result?.sentiment || {};
  const narratives = result?.narratives || [];
  const geography = result?.geography || {};
  const trends = result?.trends || [];
  const topPlaces = Object.entries(geography.top_places || {});
  const geoScopes = geography.scope_counts || {};
  const foreignCountries = Object.entries(geography.foreign_countries || {});
  const geoScopeLabels = {
    target_territory: 'Territorio objetivo',
    rest_of_country: 'Resto del país',
    international: 'Contexto internacional',
    cross_border: 'Objetivo + extranjero',
    undetermined: 'Sin ubicación verificable',
  };
  const platforms = coverage.platforms || [];
  const opinion = result?.opinion || [];

  const stanceShares = (b = {}) => {
    const favorable = b.favorable || 0;
    const critica = b.critica || 0;
    const opinionated = favorable + critica;
    return {
      favorable,
      critica,
      neutra: b.neutra || 0,
      opinionated,
      favShare: opinionated ? Math.round((100 * favorable) / opinionated) : 0,
      critShare: opinionated ? Math.round((100 * critica) / opinionated) : 0,
    };
  };

  const trend = result?.trend || null;
  const bucketLabel = { day: 'día', week: 'semana', month: 'mes' }[trend?.bucket] || 'tramo';
  let trendHtml = '';
  if (trend && (trend.points || []).length) {
    const shown = trend.points.slice(-12);
    const projection = trend.projection || [];
    const top = Math.max(
      1,
      ...shown.map((p) => p.documents || 0),
      ...projection.map((p) => p.high || 0)
    );
    const bars = [
      ...shown.map((p) => {
        const h = Math.max(2, Math.round((100 * (p.documents || 0)) / top));
        return `<div title="${escapeHtml(p.period_start)}: ${p.documents} piezas" style="flex:1;display:flex;align-items:flex-end">
          <div style="width:100%;height:${h}px;background:#2563eb;border-radius:2px 2px 0 0"></div></div>`;
      }),
      ...projection.map((p) => {
        const h = Math.max(2, Math.round((100 * (p.expected || 0)) / top));
        return `<div title="proyección ${escapeHtml(p.period_start)}: ${Math.round(p.expected)}" style="flex:1;display:flex;align-items:flex-end">
          <div style="width:100%;height:${h}px;background:#93c5fd;border-top:2px dashed #2563eb;border-radius:2px 2px 0 0"></div></div>`;
      }),
    ].join('');
    const projectionRows = projection
      .map(
        (p) => `<tr>
          <td>${escapeHtml(p.period_start)}</td>
          <td>${Math.round(p.expected)}</td>
          <td class="muted">${Math.round(p.low)} – ${Math.round(p.high)}</td>
        </tr>`
      )
      .join('');
    const scenarios = (trend.scenarios || [])
      .map(
        (s) => `<li><strong>${escapeHtml(s.nombre || '')}</strong>
          <span class="chip">${escapeHtml(s.probabilidad || '')}</span><br>
          ${escapeHtml(s.descripcion || '')}
          ${
            (s.senales || []).length
              ? `<br><span class="muted">Señales: ${escapeHtml((s.senales || []).join('; '))}</span>`
              : ''
          }</li>`
      )
      .join('');
    trendHtml = `
    <div class="card" style="margin-top:12px">
      <h2>Tendencia y proyección</h2>
      <p>Volumen <strong>${escapeHtml(trend.direction || '')}</strong> por ${bucketLabel} ·
        promedio ${escapeHtml(trend.average ?? 0)} ·
        pico ${escapeHtml(trend.peak_documents ?? 0)} el ${escapeHtml(trend.peak_period || '—')}
        ${trend.tone_direction && trend.tone_direction !== 'desconocida' ? `· tono <strong>${escapeHtml(trend.tone_direction)}</strong>` : ''}</p>
      <div style="display:flex;gap:3px;height:110px;align-items:flex-end;margin:12px 0">${bars}</div>
      <p class="muted">Azul: observado por ${bucketLabel}. Celeste punteado: proyectado.</p>
      ${
        projectionRows
          ? `<table class="table"><thead><tr><th>Desde</th><th>Esperado</th><th>Rango</th></tr></thead><tbody>${projectionRows}</tbody></table>`
          : ''
      }
      ${trend.note ? `<p style="color:#b45309">${escapeHtml(trend.note)}</p>` : ''}
      ${scenarios ? `<h3>Escenarios</h3><ul>${scenarios}</ul>` : ''}
      <p class="muted">La proyección extrapola la serie observada; un hecho nuevo puede romperla.</p>
    </div>`;
  }

  const opinionHtml = opinion
    .map((op) => {
      const aud = stanceShares(op.audience);
      const med = stanceShares(op.media);
      const opinionated = aud.opinionated + med.opinionated;
      const reliable = opinionated >= 10;
      const bar = !reliable
        ? `<p style="color:#b45309">Muestra insuficiente: solo ${opinionated} menciones con postura
           explícita (mínimo 10 para interpretar porcentajes). Amplía el periodo o agrega fuentes.</p>`
        : aud.opinionated
          ? `<div style="display:flex;height:26px;border-radius:6px;overflow:hidden;font-size:12px;color:#fff;margin:8px 0">
             <div style="width:${aud.favShare}%;background:#15803d;display:flex;align-items:center;justify-content:center">${aud.favShare}% a favor</div>
             <div style="width:${aud.critShare}%;background:#b91c1c;display:flex;align-items:center;justify-content:center">${aud.critShare}% crítica</div>
           </div>`
          : '<p class="muted">La audiencia no dejó posturas explícitas en esta muestra.</p>';
      const combinedFav = (aud.favorable || 0) + (med.favorable || 0);
      const combinedCrit = (aud.critica || 0) + (med.critica || 0);
      const unanimous =
        reliable &&
        op.classifier !== 'gemini' &&
        (combinedCrit === 0 || combinedFav === 0) &&
        combinedFav + combinedCrit > 0;
      const biasNote = unanimous
        ? `<p style="color:#b45309">Resultado casi unánime obtenido por conteo de palabras, que no
           detecta ironía ni sarcasmo: revisa las citas antes de darlo por bueno.</p>`
        : '';
      const duels = (op.duels || [])
        .map((d) => {
          const total = (d.actor_votes || 0) + (d.rival_votes || 0);
          const share = total ? Math.round((100 * (d.actor_votes || 0)) / total) : 0;
          const conclusive = total >= 5;
          const winner = !conclusive
            ? 'sin evidencia suficiente'
            : d.actor_votes === d.rival_votes
              ? 'empate'
              : d.actor_votes > d.rival_votes
                ? d.actor
                : d.rival;
          return `<tr>
            <td>${escapeHtml(d.actor)} vs ${escapeHtml(d.rival)}</td>
            <td>${escapeHtml(d.actor_votes)} – ${escapeHtml(d.rival_votes)}</td>
            <td>${conclusive ? `${share}% para ${escapeHtml(d.actor)}` : `solo ${total} comparaciones`}</td>
            <td><strong>${escapeHtml(winner)}</strong></td>
          </tr>`;
        })
        .join('');
      const quotes = (op.quotes || [])
        .map(
          (q) => `<li>
            <span class="chip">${q.stance === 'favorable' ? 'a favor' : 'crítica'}</span>
            <span class="muted">${q.voice === 'audience' ? 'audiencia' : 'medio'} · ${escapeHtml(q.source_type || '')}</span><br>
            ${escapeHtml(q.text || '')}
            ${q.url ? `<a href="${escapeHtml(q.url)}" target="_blank" rel="noopener">ver</a>` : ''}
          </li>`
        )
        .join('');
      return `
        <h3>${escapeHtml(op.actor)}</h3>
        <p class="muted">${escapeHtml(op.documents_analyzed || 0)} menciones analizadas ·
          audiencia: ${aud.favorable} a favor / ${aud.critica} críticas / ${aud.neutra} sin postura ·
          medios: ${med.favorable} / ${med.critica} / ${med.neutra}</p>
        ${bar}
        ${biasNote}
        ${
          duels
            ? `<table class="table"><thead><tr><th>Comparación</th><th>Votos</th><th>Preferencia</th><th>Gana</th></tr></thead><tbody>${duels}</tbody></table>`
            : '<p class="muted">Sin comparaciones explícitas con otros actores en esta muestra.</p>'
        }
        ${quotes ? `<ul>${quotes}</ul>` : ''}
      `;
    })
    .join('');

  container.innerHTML = `
    <h1 class="page-title">${escapeHtml(req.topic)}</h1>
    <p class="page-sub">${escapeHtml(req.territory_label)} · ${escapeHtml(req.period_start)} → ${escapeHtml(req.period_end)}</p>
    <div class="btn-row">
      <a class="btn btn-secondary" href="#/analizador">Lista</a>
      <button type="button" class="btn btn-secondary" id="refresh">Actualizar</button>
    </div>
    <div class="card" style="margin-top:12px">
      <span class="chip">${escapeHtml(statusLabel(req.status))}</span>
      <span class="muted"> · ${req.progress || 0}% · ${escapeHtml(req.current_stage || '')}</span>
      ${req.error ? `<p class="error">${escapeHtml(req.error)}</p>` : ''}
      ${
        !result
          ? `<p class="muted" style="margin-top:10px">El informe aparecerá aquí cuando termine el procesamiento (GitHub Actions / worker).</p>`
          : ''
      }
    </div>
    ${
      result
        ? `
    <div class="card" style="margin-top:12px">
      <h2>Resumen ejecutivo</h2>
      <p>${escapeHtml(result.executive_summary || '')}</p>
    </div>
    <div class="grid grid-2" style="margin-top:12px">
      <div class="card">
        <h2>Hallazgos</h2>
        <ul>${findings.map((f) => `<li>${escapeHtml(f)}</li>`).join('') || '<li class="muted">—</li>'}</ul>
      </div>
      <div class="card">
        <h2>Sentimiento global</h2>
        <p class="muted">Observaciones: ${escapeHtml(sentiment.observations ?? 0)} · score medio ${escapeHtml(sentiment.average_score ?? 0)}</p>
        <ul>${Object.entries(sentiment.labels || {})
          .map(([k, v]) => `<li>${escapeHtml(k)}: ${escapeHtml(v)}</li>`)
          .join('')}</ul>
      </div>
    </div>
    ${
      opinion.length
        ? `<div class="card" style="margin-top:12px">
      <h2>Qué se dice del actor</h2>
      ${opinionHtml}
      <p class="muted">Mide la conversación observada en las fuentes accesibles, separando la voz
      de la audiencia de la de los medios. No es una encuesta representativa de la población.</p>
    </div>`
        : ''
    }
    ${trendHtml}
    <div class="card" style="margin-top:12px">
      <h2>Actores</h2>
      <table class="table"><thead><tr><th>Actor</th><th>Menciones</th><th>Score</th><th>Citas</th></tr></thead>
      <tbody>
      ${
        actors.length
          ? actors
              .map(
                (a) => `<tr>
            <td>${escapeHtml(a.name)}</td>
            <td>${escapeHtml(a.mentions)}</td>
            <td>${escapeHtml(a.average_score)}</td>
            <td class="muted">${escapeHtml((a.sample_quotes || []).slice(0, 1).join(' · '))}</td>
          </tr>`
              )
              .join('')
          : '<tr><td colspan="4" class="muted">Sin actores aún</td></tr>'
      }
      </tbody></table>
    </div>
    <div class="grid grid-2" style="margin-top:12px">
      <div class="card">
        <h2>Narrativas</h2>
        <ul>${
          narratives.length
            ? narratives
                .map(
                  (n) =>
                    `<li><strong>${escapeHtml(n.title)}</strong> <span class="muted">(${escapeHtml(n.polarity)})</span><br>${escapeHtml(n.description || '')}<br><span class="muted">${escapeHtml((n.evidence || []).slice(0, 1).join(' · '))}</span></li>`
                )
                .join('')
            : '<li class="muted">—</li>'
        }</ul>
      </div>
      <div class="card">
        <h2>Cobertura geográfica estricta</h2>
        <p class="muted">Clasifica la relación territorial sin eliminar menciones extranjeras relevantes.</p>
        <ul>
          <li>Territorio objetivo: ${escapeHtml(geoScopes.target_territory ?? 0)}</li>
          <li>Objetivo + extranjero: ${escapeHtml(geoScopes.cross_border ?? 0)}</li>
          <li>Solo contexto internacional: ${escapeHtml(geoScopes.international ?? 0)}</li>
          ${
            geoScopes.rest_of_country != null
              ? `<li>Resto del país: ${escapeHtml(geoScopes.rest_of_country)}</li>`
              : ''
          }
          <li>Sin ubicación verificable: ${escapeHtml(geoScopes.undetermined ?? 0)}</li>
        </ul>
        ${
          foreignCountries.length
            ? `<p><strong>Países extranjeros mencionados</strong></p>
               <ul>${foreignCountries
                 .slice(0, 12)
                 .map(([country, count]) => `<li>${escapeHtml(country)}: ${escapeHtml(count)}</li>`)
                 .join('')}</ul>`
            : ''
        }
        <h3 style="margin-top:12px">Lugares mencionados</h3>
        <ul>${
          topPlaces.length
            ? topPlaces.map(([k, v]) => `<li>${escapeHtml(k)}: ${escapeHtml(v)}</li>`).join('')
            : '<li class="muted">Sin menciones geográficas detectadas</li>'
        }</ul>
        <h2 style="margin-top:12px">Evolución (volumen)</h2>
        <ul>${
          trends.length
            ? trends
                .slice(-14)
                .map((t) => `<li>${escapeHtml(t.date)}: ${escapeHtml(t.count)}</li>`)
                .join('')
            : '<li class="muted">Sin fechas publicadas en la muestra</li>'
        }</ul>
      </div>
    </div>
    <div class="card" style="margin-top:12px">
      <h2>Cobertura por plataforma</h2>
      <p class="muted">Descubiertos: ${escapeHtml(coverage.documents_discovered ?? 0)} · Incluidos: ${escapeHtml(coverage.documents_included ?? 0)}</p>
      ${
        platforms.length
          ? `<table class="table"><thead><tr><th>Plataforma</th><th>Documentos</th><th>Cómo se obtuvo</th></tr></thead>
             <tbody>${platforms
               .map(
                 (p) => `<tr>
                   <td>${escapeHtml(p.label || p.platform)}</td>
                   <td>${escapeHtml(p.documents ?? 0)}</td>
                   <td><span class="chip">${escapeHtml(COVERAGE_METHODS[p.method] || p.method)}</span>
                     ${p.note ? `<br><span class="muted">${escapeHtml(p.note)}</span>` : ''}</td>
                 </tr>`
               )
               .join('')}</tbody></table>`
          : `<ul>${Object.entries(coverage.by_source || {})
              .map(([k, v]) => `<li>${escapeHtml(k)}: ${escapeHtml(v)}</li>`)
              .join('')}</ul>`
      }
    </div>
    <div class="card" style="margin-top:12px">
      <h2>Advertencias metodológicas</h2>
      <ul>${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join('') || '<li class="muted">—</li>'}</ul>
    </div>
    <div class="card" style="margin-top:12px">
      <h2>Fuentes (muestra)</h2>
      <label for="geo-scope-filter">Filtrar por relación geográfica</label>
      <select id="geo-scope-filter">
        <option value="">Todas</option>
        ${Object.entries(geoScopeLabels)
          .map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`)
          .join('')}
      </select>
      <ul id="geo-source-list">${(docs || [])
        .map((d) => {
          const safe = /^https?:\/\//i.test(d.url || '') ? d.url : '';
          const scope = d.metadata?.geographic_scope || 'undetermined';
          const countries = d.metadata?.foreign_countries || [];
          return `<li data-geo-scope="${escapeHtml(scope)}">${
            safe
              ? `<a href="${escapeHtml(safe)}" target="_blank" rel="noopener">${escapeHtml(d.title || safe)}</a>`
              : escapeHtml(d.title || 'sin título')
          }
          <span class="muted"> · ${escapeHtml(d.publisher || '')} · ${escapeHtml(d.source_type || '')}
          · ${escapeHtml(geoScopeLabels[scope] || scope)}
          ${countries.length ? ` (${escapeHtml(countries.join(', '))})` : ''}</span></li>`;
        })
        .join('')}</ul>
    </div>
    <div class="card" style="margin-top:12px">
      <h2>Exportaciones</h2>
      <p class="muted">Artefactos privados en Storage (URLs firmadas de corta duración).</p>
      <ul id="artifact-list">${(artifacts || [])
        .map(
          (a) =>
            `<li><button type="button" class="btn btn-secondary art-dl" data-path="${escapeHtml(a.storage_path)}" data-kind="${escapeHtml(a.kind)}">Descargar ${escapeHtml(a.kind)}</button>
            <span class="muted"> · ${escapeHtml(a.storage_path)}</span></li>`
        )
        .join('') || '<li class="muted">Aún no hay archivos en Storage (el informe JSON ya está en la base).</li>'}</ul>
      <button type="button" class="btn btn-secondary" id="download-json">Descargar JSON</button>
      <button type="button" class="btn btn-secondary" id="download-csv-client">Descargar CSV (fuentes)</button>
    </div>`
        : ''
    }
  `;

  container.querySelector('#refresh').onclick = () => renderMediaAnalyzerDetail(container, id);
  const geoFilter = container.querySelector('#geo-scope-filter');
  if (geoFilter) {
    geoFilter.onchange = () => {
      const selected = geoFilter.value;
      container.querySelectorAll('#geo-source-list [data-geo-scope]').forEach((item) => {
        item.hidden = Boolean(selected && item.dataset.geoScope !== selected);
      });
    };
  }
  const dl = container.querySelector('#download-json');
  if (dl && result) {
    dl.onclick = () => {
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `radiografia_${id}.json`;
      a.click();
    };
  }
  const csvBtn = container.querySelector('#download-csv-client');
  if (csvBtn && docs) {
    csvBtn.onclick = () => {
      const header =
        'title,publisher,source_type,url,published_at,geographic_scope,source_country,foreign_countries\n';
      const rows = (docs || [])
        .map((d) =>
          [
            d.title,
            d.publisher,
            d.source_type,
            d.url,
            d.published_at,
            d.metadata?.geographic_scope || 'undetermined',
            d.metadata?.source_country || '',
            (d.metadata?.foreign_countries || []).join('; '),
          ]
            .map((x) => `"${String(x ?? '').replace(/"/g, '""')}"`)
            .join(',')
        )
        .join('\n');
      const blob = new Blob([header + rows], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `fuentes_${id}.csv`;
      a.click();
    };
  }
  container.querySelectorAll('.art-dl').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const path = btn.getAttribute('data-path');
      const kind = btn.getAttribute('data-kind') || 'file';
      if (!path) return;
      const { data, error: signErr } = await sb.storage
        .from('media-analysis-results')
        .createSignedUrl(path, 120);
      if (signErr || !data?.signedUrl) {
        alert(signErr?.message || 'No se pudo firmar la URL');
        return;
      }
      const a = document.createElement('a');
      a.href = data.signedUrl;
      a.target = '_blank';
      a.rel = 'noopener';
      a.download = `radiografia_${id}.${kind}`;
      a.click();
    });
  });

  // Auto-refresh mientras corre
  if (['pending', 'running', 'validating', 'collecting', 'extracting', 'analyzing', 'rendering'].includes(req.status)) {
    setTimeout(() => {
      if (location.hash.includes(id)) renderMediaAnalyzerDetail(container, id);
    }, 12000);
  }
}
