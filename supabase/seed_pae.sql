-- Importa el boletín PAE para el superadmin (raimundoibieta@gmail.com).
-- Ejecutar en SQL Editor si la web no lo crea sola al abrir "Mis boletines".

with admin as (
  select id from public.profiles
  where lower(email) = 'raimundoibieta@gmail.com'
  limit 1
),
ins as (
  insert into public.bulletins (
    user_id, title, short_label, audience, focus, queries, analysis_axes,
    schedule_weekday, schedule_hour, schedule_minute, active
  )
  select
    admin.id,
    'Inteligencia de ecosistema PAE',
    'PAE / Educación Chile',
    'gerencias de empresas concesionarias del PAE',
    'JUNAEB y el Programa de Alimentación Escolar (PAE), JUNJI y Fundación Integra (alimentación), MINEDUC (educación en Chile). Impacto en licitaciones, raciones, normativa y oportunidades/riesgos para concesionarias.',
    '[
      {"q":"JUNAEB","topic":"JUNAEB_PAE"},
      {"q":"Programa de Alimentación Escolar","topic":"JUNAEB_PAE"},
      {"q":"alimentación escolar JUNAEB","topic":"JUNAEB_PAE"},
      {"q":"JUNJI alimentación","topic":"JUNJI_INTEGRA"},
      {"q":"Fundación Integra colación","topic":"JUNJI_INTEGRA"},
      {"q":"MINEDUC suspensión clases","topic":"MINEDUC"},
      {"q":"Ministerio de Educación Chile","topic":"MINEDUC"}
    ]'::jsonb,
    '["licitaciones / contratos / raciones","normativa sanitaria y nutricional","presupuesto fiscal y transferencias","relación con JUNAEB, MINEDUC, JUNJI e Integra","riesgos y oportunidades para concesionarias del PAE"]'::jsonb,
    'monday', 7, 30, true
  from admin
  where not exists (
    select 1 from public.bulletins b
    where b.user_id = admin.id
      and (b.short_label ilike '%PAE%' or b.title ilike '%PAE%')
  )
  returning id
)
insert into public.bulletin_recipients (bulletin_id, email)
select ins.id, 'raimundoibieta@gmail.com'
from ins
on conflict do nothing;
