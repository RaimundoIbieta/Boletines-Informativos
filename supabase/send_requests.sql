-- Cola de pruebas de envío (botón "Probar" en la web)
-- Ejecutar en SQL Editor si el schema ya estaba aplicado.

create table if not exists public.send_requests (
  id uuid primary key default gen_random_uuid(),
  bulletin_id uuid not null references public.bulletins(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'pending'
    check (status in ('pending', 'running', 'done', 'error')),
  error text,
  created_at timestamptz not null default now(),
  processed_at timestamptz
);

create index if not exists send_requests_status_idx
  on public.send_requests (status, created_at);

alter table public.send_requests enable row level security;

drop policy if exists send_requests_owner on public.send_requests;
create policy send_requests_owner on public.send_requests for all
  using (user_id = auth.uid() or public.is_superadmin())
  with check (user_id = auth.uid() or public.is_superadmin());
