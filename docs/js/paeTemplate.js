/** Boletín PAE (espejo de config.yaml → themes.pae) */
export const PAE_BULLETIN = {
  title: 'Inteligencia de ecosistema PAE',
  short_label: 'PAE / Educación Chile',
  audience: 'gerencias de empresas concesionarias del PAE',
  focus:
    'JUNAEB y el Programa de Alimentación Escolar (PAE), JUNJI y Fundación Integra (alimentación), MINEDUC (educación en Chile). Impacto en licitaciones, raciones, normativa y oportunidades/riesgos para concesionarias.',
  queries: [
    { q: 'JUNAEB', topic: 'JUNAEB_PAE' },
    { q: 'Programa de Alimentación Escolar', topic: 'JUNAEB_PAE' },
    { q: 'alimentación escolar JUNAEB', topic: 'JUNAEB_PAE' },
    { q: 'JUNJI alimentación', topic: 'JUNJI_INTEGRA' },
    { q: 'Fundación Integra colación', topic: 'JUNJI_INTEGRA' },
    { q: 'MINEDUC suspensión clases', topic: 'MINEDUC' },
    { q: 'Ministerio de Educación Chile', topic: 'MINEDUC' },
  ],
  analysis_axes: [
    'licitaciones / contratos / raciones',
    'normativa sanitaria y nutricional',
    'presupuesto fiscal y transferencias',
    'relación con JUNAEB, MINEDUC, JUNJI e Integra',
    'riesgos y oportunidades para concesionarias del PAE',
  ],
  schedule_weekday: 'monday',
  schedule_hour: 7,
  schedule_minute: 30,
  active: true,
};

export const PAE_DEFAULT_EMAILS = ['raimundoibieta@gmail.com'];

export function isPaeBulletin(b) {
  if (!b) return false;
  const label = `${b.short_label || ''} ${b.title || ''}`.toLowerCase();
  return label.includes('pae');
}
