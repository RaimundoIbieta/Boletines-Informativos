-- Agenda semimensual: días 15 y último del mes, con secciones editoriales fijas.
-- Ejecutar una vez en Supabase SQL Editor.

alter table public.bulletins
  add column if not exists schedule_frequency text not null default 'weekly'
    check (schedule_frequency in ('weekly', 'semimonthly'));

alter table public.bulletins
  add column if not exists sections jsonb not null default '[]'::jsonb;

alter table public.bulletins
  add column if not exists output_format text not null default 'standard';

alter table public.bulletins
  drop constraint if exists bulletins_period_mode_check;

alter table public.bulletins
  add constraint bulletins_period_mode_check
    check (period_mode in ('previous_week', 'last_n_days', 'calendar_semimonthly'));

alter table public.bulletins
  drop constraint if exists bulletins_output_format_check;

alter table public.bulletins
  add constraint bulletins_output_format_check
    check (output_format in ('standard', 'panorama_sectional'));

-- Crea el boletín solicitado para el superadmin si aún no existe.
insert into public.bulletins (
  user_id, title, short_label, audience, focus, queries, analysis_axes, sections,
  schedule_frequency, schedule_weekday, schedule_hour, schedule_minute,
  period_mode, period_days, output_format, active
)
select
  u.id,
  'Panorama Quincenal de Chile y el Mundo',
  'Chile y Mundo · 15/fin',
  'directores, gerentes y analistas',
  'Análisis ejecutivo por secciones. Economía: actividad, inflación, empleo, mercados y decisiones económicas. Social: salud, educación, seguridad social y cambios sociales. Política: Gobierno, oposición, partidos, Congreso, elecciones y actores políticos. Nacional: hechos relevantes ocurridos en Chile que no correspondan principalmente a las secciones anteriores (clima, emergencias, infraestructura, justicia). Internacional: hechos del mundo (geopolítica, mercados globales, conflictos, decisiones de potencias u organismos internacionales) que puedan afectar a Chile; NO es “Chile en el extranjero”, chilenos en el exterior ni cobertura de Chile vista desde fuera. Priorizar hechos distintos, recientes y estratégicamente relevantes. Incluir varios hechos por sección con resumen corto, un análisis de cada sección y una conclusión del periodo.',
  '[
    {"q":"economía Chile Banco Central inflación empleo","topic":"ECONOMIA"},
    {"q":"Hacienda Chile crecimiento inversión mercados","topic":"ECONOMIA"},
    {"q":"empresas Chile actividad económica","topic":"ECONOMIA"},
    {"q":"salud educación vivienda Chile","topic":"SOCIAL"},
    {"q":"pensiones empleo pobreza Chile","topic":"SOCIAL"},
    {"q":"seguridad pública migración Chile sociedad","topic":"SOCIAL"},
    {"q":"Gobierno Chile gabinete oposición","topic":"POLITICA"},
    {"q":"partidos políticos Congreso Chile votación","topic":"POLITICA"},
    {"q":"elecciones encuestas política Chile","topic":"POLITICA"},
    {"q":"actualidad nacional Chile regiones emergencia lluvia","topic":"NACIONAL"},
    {"q":"infraestructura transporte medio ambiente Chile","topic":"NACIONAL"},
    {"q":"justicia tribunales Contraloría Chile","topic":"NACIONAL"},
    {"q":"geopolítica mundial conflicto guerra impacto Chile","topic":"INTERNACIONAL"},
    {"q":"Estados Unidos China Europa comercio guerra aranceles","topic":"INTERNACIONAL"},
    {"q":"Fed FMI OPEP mercados globales impacto América Latina Chile","topic":"INTERNACIONAL"}
  ]'::jsonb,
  '[
    "principales hechos y decisiones del periodo",
    "impacto para Chile y para tomadores de decisión",
    "actores, instituciones y correlación de fuerzas",
    "riesgos de corto y mediano plazo",
    "oportunidades y señales a monitorear",
    "conexiones entre las cinco secciones"
  ]'::jsonb,
  '["Economía","Social","Política","Nacional","Internacional"]'::jsonb,
  'semimonthly', 'monday', 18, 30, 'calendar_semimonthly', 15, 'panorama_sectional', true
from auth.users u
where lower(u.email) = 'raimundoibieta@gmail.com'
  and not exists (
    select 1
    from public.bulletins b
    where b.user_id = u.id
      and b.title = 'Panorama Quincenal de Chile y el Mundo'
  );

insert into public.bulletin_recipients (bulletin_id, email)
select b.id, 'raimundoibieta@gmail.com'
from public.bulletins b
join auth.users u on u.id = b.user_id
where lower(u.email) = 'raimundoibieta@gmail.com'
  and b.title = 'Panorama Quincenal de Chile y el Mundo'
on conflict (bulletin_id, email) do nothing;
