-- Formato editorial del Panorama (resumen corto + síntesis por sección + conclusión).
-- Ejecutar una vez en Supabase SQL Editor.

alter table public.bulletins
  add column if not exists output_format text not null default 'standard';

alter table public.bulletins
  drop constraint if exists bulletins_output_format_check;

alter table public.bulletins
  add constraint bulletins_output_format_check
    check (output_format in ('standard', 'panorama_sectional'));

-- Asigna el perfil panorama al boletín Chile y Mundo; el resto queda standard.
update public.bulletins
set
  output_format = 'panorama_sectional',
  short_label = case
    when short_label like '%1/15%' then 'Chile y Mundo · 15/fin'
    else short_label
  end
where title = 'Panorama Quincenal de Chile y el Mundo'
   or short_label ilike '%chile y mundo%';
