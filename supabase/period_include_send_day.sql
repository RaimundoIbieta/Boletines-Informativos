-- El periodo debe incluir el día del envío: un boletín del viernes 18:30 tiene
-- que considerar lo que pasó ese mismo viernes.
-- Ejecutar después de period_selection.sql.

alter table public.bulletins
  alter column period_mode set default 'last_n_days';

update public.bulletins
   set period_mode = 'last_n_days',
       period_days = case when period_days between 1 and 31 then period_days else 7 end,
       updated_at = now()
 where period_mode is null
    or period_mode = 'previous_week';
