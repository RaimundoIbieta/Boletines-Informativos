-- Boletines Informativos · esquema Supabase (plan free)
-- Ejecutar en: SQL Editor → New query → Run

-- Perfiles
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text unique not null,
  name text,
  role text not null default 'user' check (role in ('superadmin', 'user')),
  disabled boolean not null default false,
  created_at timestamptz not null default now()
);

-- Planes
create table if not exists public.plans (
  id text primary key,
  name text not null,
  max_bulletins int not null default 1,
  price_clp int not null default 0,
  description text,
  active boolean not null default true
);

insert into public.plans (id, name, max_bulletins, price_clp, description) values
  ('basic', 'Básico', 1, 49990, '1 boletín semanal personalizado'),
  ('pro', 'Pro', 3, 99990, 'Hasta 3 boletines (incluye 2 o 3 temáticas)'),
  ('business', 'Empresa', 10, 199990, 'Hasta 10 boletines para tu equipo')
on conflict (id) do update set
  name = excluded.name,
  max_bulletins = excluded.max_bulletins,
  price_clp = excluded.price_clp,
  description = excluded.description;

-- Suscripciones
create table if not exists public.subscriptions (
  email text primary key,
  user_id uuid references auth.users(id) on delete set null,
  plan text not null references public.plans(id) default 'basic',
  until timestamptz,
  activated_at timestamptz,
  granted_by text,
  updated_at timestamptz not null default now()
);

-- Boletines del usuario (configuración)
create table if not exists public.bulletins (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  short_label text not null,
  audience text default '',
  focus text not null default '',
  queries jsonb not null default '[]'::jsonb,
  analysis_axes jsonb not null default '[]'::jsonb,
  schedule_weekday text not null default 'monday',
  schedule_hour int not null default 7,
  schedule_minute int not null default 30,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists bulletins_user_id_idx on public.bulletins(user_id);

-- Destinatarios por boletín
create table if not exists public.bulletin_recipients (
  id uuid primary key default gen_random_uuid(),
  bulletin_id uuid not null references public.bulletins(id) on delete cascade,
  email text not null,
  created_at timestamptz not null default now(),
  unique (bulletin_id, email)
);

-- Historial de envíos / PDFs
create table if not exists public.bulletin_runs (
  id uuid primary key default gen_random_uuid(),
  bulletin_id uuid not null references public.bulletins(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  periodo_inicio date,
  periodo_fin date,
  noticias int default 0,
  pdf_url text,
  drive_url text,
  status text not null default 'published',
  created_at timestamptz not null default now()
);

-- Trigger: crear profile al registrarse
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
declare
  admin_email text := 'raimundoibieta@gmail.com';
begin
  insert into public.profiles (id, email, name, role)
  values (
    new.id,
    lower(new.email),
    coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)),
    case when lower(new.email) = admin_email then 'superadmin' else 'user' end
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- RLS
alter table public.profiles enable row level security;
alter table public.plans enable row level security;
alter table public.subscriptions enable row level security;
alter table public.bulletins enable row level security;
alter table public.bulletin_recipients enable row level security;
alter table public.bulletin_runs enable row level security;

-- Helpers
create or replace function public.is_superadmin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = 'superadmin' and p.disabled = false
  );
$$;

-- profiles policies
drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles for select
  using (auth.uid() = id or public.is_superadmin());

drop policy if exists profiles_update_self on public.profiles;
create policy profiles_update_self on public.profiles for update
  using (auth.uid() = id or public.is_superadmin());

drop policy if exists profiles_insert_self on public.profiles;
create policy profiles_insert_self on public.profiles for insert
  with check (auth.uid() = id or public.is_superadmin());

-- plans: todos leen
drop policy if exists plans_select on public.plans;
create policy plans_select on public.plans for select using (true);

-- subscriptions
drop policy if exists subs_select on public.subscriptions;
create policy subs_select on public.subscriptions for select
  using (email = (select email from public.profiles where id = auth.uid()) or public.is_superadmin());

drop policy if exists subs_upsert_admin on public.subscriptions;
create policy subs_upsert_admin on public.subscriptions for all
  using (public.is_superadmin())
  with check (public.is_superadmin());

drop policy if exists subs_insert_self_demo on public.subscriptions;
create policy subs_insert_self_demo on public.subscriptions for insert
  with check (email = (select email from public.profiles where id = auth.uid()));

drop policy if exists subs_update_self_demo on public.subscriptions;
create policy subs_update_self_demo on public.subscriptions for update
  using (email = (select email from public.profiles where id = auth.uid()));

-- bulletins
drop policy if exists bulletins_owner on public.bulletins;
create policy bulletins_owner on public.bulletins for all
  using (user_id = auth.uid() or public.is_superadmin())
  with check (user_id = auth.uid() or public.is_superadmin());

-- recipients
drop policy if exists recipients_owner on public.bulletin_recipients;
create policy recipients_owner on public.bulletin_recipients for all
  using (
    exists (select 1 from public.bulletins b where b.id = bulletin_id and (b.user_id = auth.uid() or public.is_superadmin()))
  )
  with check (
    exists (select 1 from public.bulletins b where b.id = bulletin_id and (b.user_id = auth.uid() or public.is_superadmin()))
  );

-- runs
drop policy if exists runs_owner on public.bulletin_runs;
create policy runs_owner on public.bulletin_runs for all
  using (user_id = auth.uid() or public.is_superadmin())
  with check (user_id = auth.uid() or public.is_superadmin());

-- Cola de pruebas de envío (botón Probar en la web)
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
