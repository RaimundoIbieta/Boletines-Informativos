/**
 * Sugiere búsquedas web y ejes de análisis a partir del título/enfoque.
 * Intenta la Edge Function de Supabase (Gemini); si no está desplegada, usa un generador local.
 */

import { client } from './auth.js';

const STOP = new Set([
  'el', 'la', 'los', 'las', 'de', 'del', 'y', 'o', 'en', 'un', 'una', 'para', 'por', 'con',
  'que', 'se', 'al', 'a', 'su', 'sus', 'the', 'and', 'or', 'of', 'to', 'boletin', 'boletín',
  'semanal', 'chile', 'inteligencia', 'ecosistema',
]);

function topicFrom(text) {
  const t = (text || '')
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 28);
  return t || 'GENERAL';
}

function keywords(...parts) {
  const raw = parts.filter(Boolean).join(' ');
  const words = raw
    .toLowerCase()
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .replace(/[^a-z0-9áéíóúñü\s]/gi, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 3 && !STOP.has(w));
  const uniq = [];
  for (const w of words) {
    if (!uniq.includes(w)) uniq.push(w);
    if (uniq.length >= 8) break;
  }
  return uniq;
}

/**
 * Consultas de actualidad por dominio. Sin esto, un boletín de política se
 * arma con frases genéricas y pierde los hechos del día (un cambio de
 * gabinete, por ejemplo, no aparece buscando "política chilena").
 */
const NEWS_PACKS = [
  {
    test: /pol[ií]tic|gobierno|gabinete|congreso|electoral|moneda|estado/i,
    queries: [
      { q: 'cambio de gabinete Chile ministro', topic: 'GOBIERNO' },
      { q: 'renuncia ministro Chile', topic: 'GOBIERNO' },
      { q: 'oposición Chile gobierno controversia', topic: 'OPOSICION' },
      { q: 'partidos políticos Chile coalición', topic: 'PARTIDOS' },
      { q: 'Congreso Chile proyecto de ley votación', topic: 'LEGISLATIVO' },
    ],
  },
  {
    test: /miner|cobre|codelco|litio/i,
    queries: [
      { q: 'Codelco OR cobre Chile producción', topic: 'MINERIA' },
      { q: 'litio Chile contrato OR royalty', topic: 'MINERIA' },
    ],
  },
  {
    test: /salud|isapre|fonasa|hospital/i,
    queries: [
      { q: 'Ministerio de Salud Chile anuncio', topic: 'SALUD' },
      { q: 'isapres OR Fonasa Chile reforma', topic: 'SALUD' },
    ],
  },
  {
    test: /educaci[oó]n|escolar|mineduc|universidad/i,
    queries: [
      { q: 'MINEDUC Chile anuncio', topic: 'EDUCACION' },
      { q: 'educación Chile reforma OR presupuesto', topic: 'EDUCACION' },
    ],
  },
];

function newsPackFor({ title = '', short_label = '', focus = '' }) {
  const context = `${title} ${short_label} ${focus}`;
  return NEWS_PACKS.find((p) => p.test.test(context));
}

function addNewsPack(suggestion, input) {
  const pack = newsPackFor(input);
  if (!pack) return suggestion;
  const combined = [...pack.queries, ...(suggestion.queries || [])];
  const seen = new Set();
  const queries = combined.filter((row) => {
    const key = String(row?.q || '').trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return { ...suggestion, queries: queries.slice(0, 10) };
}

/** "PAE / Educación Chile" → "PAE Educación": sin barras ni Chile repetido. */
function searchLabel(label) {
  return (label || '')
    .replace(/[\/|]+/g, ' ')
    .replace(/\bchile(n[ao]s?)?\b/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function withChile(text) {
  const t = (text || '').trim();
  if (!t) return 'Chile';
  return /\bchile\b/i.test(t) ? t : `${t} Chile`;
}

/** Generador local (sin API): base editable para el usuario. */
export function localSuggest({ title, short_label, audience, focus }) {
  const label = short_label || title || 'temática';
  const theme = topicFrom(short_label || title);
  const base = searchLabel(label) || searchLabel(title) || 'actualidad';
  const kws = keywords(title, short_label, focus);
  const main = kws[0] || base;
  const second = kws[1] || '';

  const pack = newsPackFor({ title, short_label, focus });

  const queries = [
    ...(pack ? pack.queries : []),
    { q: withChile(base), topic: theme },
    ...(second ? [{ q: withChile(`${main} ${second}`), topic: theme }] : []),
    { q: `${base} regulación OR ley Chile`, topic: `${theme}_NORMA` },
    { q: `${base} licitación OR contrato Chile`, topic: `${theme}_MERCADO` },
  ];

  const who = audience || 'tomadores de decisión';
  const analysis_axes = [
    `impacto en ${who}`,
    'riesgos operativos, legales y reputacionales',
    'oportunidades comerciales y de posicionamiento',
    'cambios normativos, licitaciones o presupuesto',
    'actores clave (Estado, privados, gremios)',
    `señales de corto plazo para ${label}`,
  ];

  if (focus) {
    const tip = focus.trim().split(/[.!\n]/)[0].trim().slice(0, 90);
    if (tip) analysis_axes.unshift(tip);
  }

  return {
    queries: queries.slice(0, 7),
    analysis_axes: analysis_axes.slice(0, 7),
    source: 'local',
  };
}

async function suggestViaEdge(payload) {
  const sb = client();
  const { data, error } = await sb.functions.invoke('suggest-bulletin', {
    body: payload,
  });
  if (error) throw error;
  if (!data?.queries?.length) throw new Error('La IA no devolvió búsquedas.');
  return {
    queries: data.queries,
    analysis_axes: data.analysis_axes || [],
    source: 'gemini',
  };
}

/**
 * @returns {{ queries: {q:string,topic:string}[], analysis_axes: string[], source: string }}
 */
export async function suggestBulletinFields(input) {
  const title = (input.title || '').trim();
  const short_label = (input.short_label || '').trim();
  const audience = (input.audience || '').trim();
  const focus = (input.focus || '').trim();
  if (!title && !short_label && !focus) {
    throw new Error('Completa al menos título, etiqueta o enfoque antes de sugerir.');
  }
  try {
    const input = { title, short_label, audience, focus };
    return addNewsPack(await suggestViaEdge(input), input);
  } catch {
    return localSuggest({ title, short_label, audience, focus });
  }
}

export function formatQueries(queries) {
  return (queries || []).map((x) => `${x.q} | ${x.topic || 'GENERAL'}`).join('\n');
}

export function formatAxes(axes) {
  return (axes || []).join('\n');
}
