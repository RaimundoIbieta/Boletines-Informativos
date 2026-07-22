-- Actualizar precios (ejecutar si ya corriste el schema antes)
update public.plans set
  name = 'Básico',
  max_bulletins = 1,
  price_clp = 49990,
  description = '1 boletín semanal personalizado'
where id = 'basic';

update public.plans set
  name = 'Pro',
  max_bulletins = 3,
  price_clp = 99990,
  description = 'Hasta 3 boletines (incluye 2 o 3 temáticas)'
where id = 'pro';

update public.plans set
  name = 'Empresa',
  max_bulletins = 10,
  price_clp = 199990,
  description = 'Hasta 10 boletines para tu equipo'
where id = 'business';
