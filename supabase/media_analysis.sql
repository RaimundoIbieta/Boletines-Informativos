-- Analizador de Medios bajo demanda
-- Ejecutar en SQL Editor de Supabase.

-- Endurecer políticas existentes (piloto seguro)
drop policy if exists profiles_update_self on public.profiles;
create policy profiles_update_self on public.profiles for update
  using (auth.uid() = id or public.is_superadmin())
  with check (
    public.is_superadmin()
    or (
      auth.uid() = id
      and role = (select p.role from public.profiles p where p.id = auth.uid())
      and disabled = (select p.disabled from public.profiles p where p.id = auth.uid())
    )
  );

drop policy if exists subs_insert_self_demo on public.subscriptions;
drop policy if exists subs_update_self_demo on public.subscriptions;

drop policy if exists send_requests_owner on public.send_requests;
create policy send_requests_select on public.send_requests for select
  using (user_id = auth.uid() or public.is_superadmin());
create policy send_requests_insert on public.send_requests for insert
  with check (user_id = auth.uid() or public.is_superadmin());
-- Updates de status solo vía service_role (sin política de update para usuarios)

drop policy if exists runs_owner on public.bulletin_runs;
create policy runs_select on public.bulletin_runs for select
  using (user_id = auth.uid() or public.is_superadmin());
create policy runs_insert_admin on public.bulletin_runs for insert
  with check (public.is_superadmin() or user_id = auth.uid());

-- Solicitudes de análisis
create table if not exists public.media_analysis_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  topic text not null,
  actors jsonb not null default '[]'::jsonb,
  include_terms jsonb not null default '[]'::jsonb,
  exclude_terms jsonb not null default '[]'::jsonb,
  territory_level text not null default 'national'
    check (territory_level in ('national', 'regional', 'communal')),
  region_code text,
  commune_code text,
  territory_label text not null default 'Chile',
  period_start date not null,
  period_end date not null,
  open_sources boolean not null default true,
  enabled_sources jsonb not null default '["news","youtube","reddit","bluesky","mastodon","indexed"]'::jsonb,
  status text not null default 'pending'
    check (status in (
      'pending','validating','collecting','extracting','analyzing',
      'rendering','running','completed','partial','failed','cancelled'
    )),
  progress smallint not null default 0 check (progress between 0 and 100),
  current_stage text default '',
  error text,
  attempts int not null default 0,
  locked_at timestamptz,
  locked_by text,
  configuration jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  check (period_end >= period_start),
  check (
    (territory_level = 'national')
    or (territory_level = 'regional' and region_code is not null)
    or (territory_level = 'communal' and region_code is not null and commune_code is not null)
  )
);

create index if not exists media_analysis_requests_status_idx
  on public.media_analysis_requests (status, created_at);
create index if not exists media_analysis_requests_user_idx
  on public.media_analysis_requests (user_id, created_at desc);

-- Insumos (URLs / archivos / búsquedas abiertas)
create table if not exists public.media_analysis_inputs (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.media_analysis_requests(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('url', 'file', 'open_search')),
  original_url text,
  storage_path text,
  file_name text,
  mime_type text,
  size_bytes bigint,
  sha256 text,
  status text not null default 'pending'
    check (status in ('pending', 'processed', 'rejected', 'failed')),
  extracted_text_path text,
  error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  processed_at timestamptz
);

create index if not exists media_analysis_inputs_request_idx
  on public.media_analysis_inputs (request_id);

-- Documentos descubiertos / ingeridos
create table if not exists public.media_analysis_documents (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.media_analysis_requests(id) on delete cascade,
  input_id uuid references public.media_analysis_inputs(id) on delete set null,
  source_type text not null default 'news',
  title text,
  publisher text,
  author text,
  url text,
  canonical_url text,
  published_at timestamptz,
  language text,
  excerpt text,
  content_hash text,
  territory_match text,
  included boolean not null default true,
  exclusion_reason text,
  engagement jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists media_analysis_documents_request_idx
  on public.media_analysis_documents (request_id);

-- Observaciones (sentimiento / geografía / narrativas)
create table if not exists public.media_analysis_observations (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.media_analysis_requests(id) on delete cascade,
  document_id uuid references public.media_analysis_documents(id) on delete cascade,
  kind text not null check (kind in ('sentiment', 'geo', 'narrative', 'actor', 'story')),
  target text,
  label text,
  score numeric,
  confidence numeric,
  evidence text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists media_analysis_observations_request_idx
  on public.media_analysis_observations (request_id);

-- Resultado canónico
create table if not exists public.media_analysis_results (
  request_id uuid primary key references public.media_analysis_requests(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  executive_summary text,
  findings jsonb not null default '[]'::jsonb,
  actors jsonb not null default '[]'::jsonb,
  narratives jsonb not null default '[]'::jsonb,
  trends jsonb not null default '[]'::jsonb,
  sentiment jsonb not null default '{}'::jsonb,
  geography jsonb not null default '{}'::jsonb,
  coverage_metrics jsonb not null default '{}'::jsonb,
  methodology jsonb not null default '{}'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  model_provider text,
  model_name text,
  prompt_version text default 'media-v1',
  created_at timestamptz not null default now()
);

-- Artefactos privados (PDF / CSV / JSON / MD)
create table if not exists public.media_analysis_artifacts (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.media_analysis_requests(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('pdf', 'markdown', 'json', 'csv', 'html')),
  storage_path text not null,
  mime_type text,
  size_bytes bigint,
  created_at timestamptz not null default now()
);

create index if not exists media_analysis_artifacts_request_idx
  on public.media_analysis_artifacts (request_id);

-- RLS
alter table public.media_analysis_requests enable row level security;
alter table public.media_analysis_inputs enable row level security;
alter table public.media_analysis_documents enable row level security;
alter table public.media_analysis_observations enable row level security;
alter table public.media_analysis_results enable row level security;
alter table public.media_analysis_artifacts enable row level security;

drop policy if exists media_requests_select on public.media_analysis_requests;
create policy media_requests_select on public.media_analysis_requests for select
  using (user_id = auth.uid() or public.is_superadmin());

drop policy if exists media_requests_insert on public.media_analysis_requests;
create policy media_requests_insert on public.media_analysis_requests for insert
  with check (
    (user_id = auth.uid() or public.is_superadmin())
    and public.is_superadmin()  -- piloto: solo admin
  );

drop policy if exists media_requests_update_owner_cancel on public.media_analysis_requests;
create policy media_requests_update_owner_cancel on public.media_analysis_requests for update
  using (user_id = auth.uid() or public.is_superadmin())
  with check (
    public.is_superadmin()
    or (user_id = auth.uid() and status in ('pending', 'cancelled'))
  );

drop policy if exists media_inputs_select on public.media_analysis_inputs;
create policy media_inputs_select on public.media_analysis_inputs for select
  using (user_id = auth.uid() or public.is_superadmin());

drop policy if exists media_inputs_insert on public.media_analysis_inputs;
create policy media_inputs_insert on public.media_analysis_inputs for insert
  with check (
    user_id = auth.uid()
    and public.is_superadmin()
    and exists (
      select 1 from public.media_analysis_requests r
      where r.id = request_id and r.user_id = auth.uid() and r.status = 'pending'
    )
  );

drop policy if exists media_inputs_delete on public.media_analysis_inputs;
create policy media_inputs_delete on public.media_analysis_inputs for delete
  using (
    user_id = auth.uid()
    and exists (
      select 1 from public.media_analysis_requests r
      where r.id = request_id and r.status = 'pending'
    )
  );

drop policy if exists media_docs_select on public.media_analysis_documents;
create policy media_docs_select on public.media_analysis_documents for select
  using (
    exists (
      select 1 from public.media_analysis_requests r
      where r.id = request_id and (r.user_id = auth.uid() or public.is_superadmin())
    )
  );

drop policy if exists media_obs_select on public.media_analysis_observations;
create policy media_obs_select on public.media_analysis_observations for select
  using (
    exists (
      select 1 from public.media_analysis_requests r
      where r.id = request_id and (r.user_id = auth.uid() or public.is_superadmin())
    )
  );

drop policy if exists media_results_select on public.media_analysis_results;
create policy media_results_select on public.media_analysis_results for select
  using (user_id = auth.uid() or public.is_superadmin());

drop policy if exists media_artifacts_select on public.media_analysis_artifacts;
create policy media_artifacts_select on public.media_analysis_artifacts for select
  using (user_id = auth.uid() or public.is_superadmin());

-- RPC: crear solicitud (solo superadmin en piloto)
create or replace function public.create_media_analysis_request(
  p_topic text,
  p_period_start date,
  p_period_end date,
  p_territory_level text default 'national',
  p_region_code text default null,
  p_commune_code text default null,
  p_territory_label text default 'Chile',
  p_actors jsonb default '[]'::jsonb,
  p_include_terms jsonb default '[]'::jsonb,
  p_exclude_terms jsonb default '[]'::jsonb,
  p_enabled_sources jsonb default '["news","youtube","reddit","bluesky","mastodon","indexed"]'::jsonb,
  p_urls jsonb default '[]'::jsonb,
  p_configuration jsonb default '{}'::jsonb
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  rid uuid;
  url text;
begin
  if auth.uid() is null then
    raise exception 'No autenticado';
  end if;
  if not public.is_superadmin() then
    raise exception 'Piloto: solo el administrador puede crear análisis de medios';
  end if;
  if p_period_end < p_period_start then
    raise exception 'period_end debe ser >= period_start';
  end if;
  if p_period_end - p_period_start > 730 then
    raise exception 'Periodo máximo: 2 años';
  end if;

  insert into public.media_analysis_requests (
    user_id, topic, actors, include_terms, exclude_terms,
    territory_level, region_code, commune_code, territory_label,
    period_start, period_end, enabled_sources, configuration, status, progress, current_stage
  ) values (
    auth.uid(), trim(p_topic), coalesce(p_actors, '[]'::jsonb),
    coalesce(p_include_terms, '[]'::jsonb), coalesce(p_exclude_terms, '[]'::jsonb),
    p_territory_level, p_region_code, p_commune_code, coalesce(nullif(trim(p_territory_label), ''), 'Chile'),
    p_period_start, p_period_end, coalesce(p_enabled_sources, '[]'::jsonb),
    coalesce(p_configuration, '{}'::jsonb), 'pending', 0, 'queued'
  ) returning id into rid;

  for url in select jsonb_array_elements_text(coalesce(p_urls, '[]'::jsonb))
  loop
    if length(trim(url)) > 0 then
      insert into public.media_analysis_inputs (request_id, user_id, kind, original_url, status)
      values (rid, auth.uid(), 'url', trim(url), 'pending');
    end if;
  end loop;

  return rid;
end;
$$;

grant execute on function public.create_media_analysis_request to authenticated;

-- RPC: reclamar siguiente solicitud (worker con service_role)
-- p_request_id opcional: reclama esa fila si está pending (o reintenta failed/partial).
create or replace function public.claim_media_analysis_request(
  p_worker_id text,
  p_request_id uuid default null
)
returns public.media_analysis_requests
language plpgsql
security definer
set search_path = public
as $$
declare
  row public.media_analysis_requests;
begin
  if p_request_id is not null then
    select * into row
    from public.media_analysis_requests
    where id = p_request_id
      and status in ('pending', 'failed', 'partial')
    for update skip locked;
  else
    select * into row
    from public.media_analysis_requests
    where status = 'pending'
    order by created_at asc
    for update skip locked
    limit 1;
  end if;

  if not found then
    return null;
  end if;

  update public.media_analysis_requests
  set status = 'running',
      progress = 5,
      current_stage = 'claimed',
      attempts = attempts + 1,
      locked_at = now(),
      locked_by = p_worker_id,
      started_at = coalesce(started_at, now()),
      error = null,
      updated_at = now()
  where id = row.id
  returning * into row;

  return row;
end;
$$;

grant execute on function public.claim_media_analysis_request(text, uuid) to service_role;

-- Storage buckets privados
insert into storage.buckets (id, name, public)
values
  ('media-analysis-inputs', 'media-analysis-inputs', false),
  ('media-analysis-results', 'media-analysis-results', false)
on conflict (id) do nothing;

drop policy if exists media_inputs_storage_owner on storage.objects;
create policy media_inputs_storage_owner on storage.objects for all
  using (
    bucket_id = 'media-analysis-inputs'
    and public.is_superadmin()
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'media-analysis-inputs'
    and public.is_superadmin()
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists media_results_storage_owner on storage.objects;
create policy media_results_storage_owner on storage.objects for select
  using (
    bucket_id = 'media-analysis-results'
    and (public.is_superadmin() or (storage.foldername(name))[1] = auth.uid()::text)
  );
