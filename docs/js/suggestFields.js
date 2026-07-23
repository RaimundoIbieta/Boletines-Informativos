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

/** Generador local (sin API): base editable para el usuario. */
export function localSuggest({ title, short_label, audience, focus }) {
  const label = short_label || title || 'temática';
  const theme = topicFrom(short_label || title);
  const kws = keywords(title, short_label, focus);
  const main = kws[0] || label;
  const second = kws[1] || 'Chile';
  const third = kws[2] || kws[0] || label;

  const queries = [
    { q: `${main} Chile`, topic: theme },
    { q: `${label}`, topic: theme },
    { q: `${main} ${second}`, topic: theme },
    { q: `${third} regulación OR ley Chile`, topic: `${theme}_NORMA` },
    { q: `${main} licitación OR contrato Chile`, topic: `${theme}_MERCADO` },
    { q: `Ministerio ${main} Chile`, topic: 'POLITICA' },
    { q: `${audience ? audience.split(/\s+/).slice(0, 3).join(' ') : 'industria'} ${main}`, topic: theme },
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
    return await suggestViaEdge({ title, short_label, audience, focus });
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
