-- Periodo de selección de noticias (ejecutar en SQL Editor si el schema ya existía).

alter table public.bulletins
  add column if not exists period_mode text not null default 'previous_week'
    check (period_mode in ('previous_week', 'last_n_days'));

alter table public.bulletins
  add column if not exists period_days int not null default 7
    check (period_days >= 1 and period_days <= 31);

alter table public.send_requests
  add column if not exists periodo_inicio date;

alter table public.send_requests
  add column if not exists periodo_fin date;
