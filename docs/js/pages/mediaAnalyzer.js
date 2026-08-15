import { client, getUser, isSuperAdmin } from './auth.js';
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
    <h1 class="page-title">Nuevo análisis de medios</h1>
    <p class="page-sub">Define el tema, territorio y periodo. Puedes aportar enlaces de X/Instagram/Facebook/TikTok para complementar la cobertura abierta.</p>
    <div class="card">
      <label>Tema</label>
      <input id="topic" placeholder="Ej. quién será el próximo presidente de Chile" />
      <label>Actores / objetivos de sentimiento (uno por línea)</label>
      <textarea id="actors" placeholder="José Antonio Kast&#10;candidato A&#10;candidato B"></textarea>
      <div class="grid grid-3">
        <div>
          <label>Nivel territorial</label>
          <select id="territory_level">
            <option value="national">Nacional</option>
            <option value="regional">Regional</option>
            <option value="communal">Comunal</option>
          </select>
        </div>
        <div id="region-wrap" style="display:none">
          <label>Región</label>
          <select id="region_code">
            <option value="">—</option>
            ${REGIONS.map(([c, n]) => `<option value="${c}">${escapeHtml(n)}</option>`).join('')}
          </select>
        </div>
        <div id="commune-wrap" style="display:none">
          <label>Comuna (código o nombre)</label>
          <input id="commune_code" placeholder="Ej. 13101 o Santiago" />
        </div>
      </div>
      <label>Etiqueta territorial</label>
      <input id="territory_label" value="Chile" />
      <div class="grid grid-2">
        <div>
          <label>Desde</label>
          <input id="period_start" type="date" value="${period.start}" />
        </div>
        <div>
          <label>Hasta</label>
          <input id="period_end" type="date" value="${period.end}" />
        </div>
      </div>
      <p class="muted">Por defecto 30 días. Como admin puedes ampliar hasta 2 años (las redes gratuitas tendrán cobertura histórica parcial).</p>
      <label>Incluir términos (opcional)</label>
      <textarea id="include" placeholder="elección&#10;encuesta"></textarea>
      <label>Excluir términos (opcional)</label>
      <textarea id="exclude"></textarea>
      <label>Fuentes abiertas</label>
      <div class="grid grid-3">
        ${['news', 'youtube', 'reddit', 'bluesky', 'mastodon', 'indexed']
          .map(
            (s) => `<label style="text-transform:none;letter-spacing:0;font-size:.95rem;display:flex;gap:8px;align-items:center">
              <input type="checkbox" class="src" value="${s}" checked /> ${s}
            </label>`
          )
          .join('')}
      </div>
      <label>URLs de redes restringidas / aportes (una por línea)</label>
      <textarea id="urls" placeholder="https://x.com/...&#10;https://www.instagram.com/p/..."></textarea>
      <label>Archivos (txt, md, csv, json, html, pdf)</label>
      <input id="files" type="file" multiple accept=".txt,.md,.csv,.json,.html,.htm,.pdf,text/plain,application/pdf" />
      <div class="btn-row">
        <button type="button" class="btn" id="submit">Generar radiografía</button>
        <a class="btn btn-secondary" href="#/analizador">Cancelar</a>
      </div>
      <p class="error" id="err"></p>
      <p class="muted" id="ok"></p>
    </div>
  `;

  const levelEl = container.querySelector('#territory_level');
  const syncTerritory = () => {
    const level = levelEl.value;
    container.querySelector('#region-wrap').style.display =
      level === 'regional' || level === 'communal' ? '' : 'none';
    container.querySelector('#commune-wrap').style.display = level === 'communal' ? '' : 'none';
    if (level === 'national') container.querySelector('#territory_label').value = 'Chile';
  };
  levelEl.onchange = syncTerritory;
  container.querySelector('#region_code').onchange = () => {
    const opt = container.querySelector('#region_code').selectedOptions[0];
    if (opt?.value) container.querySelector('#territory_label').value = opt.textContent;
  };

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
        p_configuration: { default_window_days: 30, max_years: 2 },
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
        <h2>Territorio / menciones</h2>
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
      <h2>Cobertura</h2>
      <p class="muted">Descubiertos: ${escapeHtml(coverage.documents_discovered ?? 0)} · Incluidos: ${escapeHtml(coverage.documents_included ?? 0)}</p>
      <ul>${Object.entries(coverage.by_source || {})
        .map(([k, v]) => `<li>${escapeHtml(k)}: ${escapeHtml(v)}</li>`)
        .join('')}</ul>
      ${
        coverage.connector_errors
          ? `<p class="muted">Errores de conectores: ${escapeHtml(JSON.stringify(coverage.connector_errors))}</p>`
          : ''
      }
    </div>
    <div class="card" style="margin-top:12px">
      <h2>Advertencias metodológicas</h2>
      <ul>${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join('') || '<li class="muted">—</li>'}</ul>
    </div>
    <div class="card" style="margin-top:12px">
      <h2>Fuentes (muestra)</h2>
      <ul>${(docs || [])
        .map((d) => {
          const safe = /^https?:\/\//i.test(d.url || '') ? d.url : '';
          return `<li>${
            safe
              ? `<a href="${escapeHtml(safe)}" target="_blank" rel="noopener">${escapeHtml(d.title || safe)}</a>`
              : escapeHtml(d.title || 'sin título')
          }
          <span class="muted"> · ${escapeHtml(d.publisher || '')} · ${escapeHtml(d.source_type || '')}</span></li>`;
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
      const header = 'title,publisher,source_type,url,published_at\n';
      const rows = (docs || [])
        .map((d) =>
          [d.title, d.publisher, d.source_type, d.url, d.published_at]
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
