-- Datos de terceros (licencias): reemplaza el uso operativo del inventario telecom en la app.
-- Ejecutar en SQL Editor después de migration_002 y 003.
-- Si el INSERT al bucket falla, creá **license-photos** en Dashboard → Storage (privado, ≤5 MB, jpeg/png/webp).

do $$ begin
  create type public.license_record_status as enum (
    'vigente',
    'por_vencer',
    'vencida',
    'suspendida',
    'revocada',
    'en_tramite'
  );
exception when duplicate_object then null;
end $$;

create table if not exists public.third_party_identities (
  id uuid primary key default gen_random_uuid(),
  first_name text not null,
  last_name text not null,
  address_line text,
  license_number text not null,
  license_status public.license_record_status not null default 'vigente',
  license_issuing_state text,
  date_of_birth date,
  license_issued_date date,
  license_expiry_date date not null,
  photo_front_path text,
  photo_back_path text,
  use_doordash boolean not null default false,
  use_instacart boolean not null default false,
  use_lyft boolean not null default false,
  use_ubereats boolean not null default false,
  use_spark_driver boolean not null default false,
  use_amazon_flex boolean not null default false,
  use_veho boolean not null default false,
  use_other boolean not null default false,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_tpi_expiry on public.third_party_identities (license_expiry_date);
create index if not exists idx_tpi_name on public.third_party_identities (last_name, first_name);

drop trigger if exists tr_tpi_updated on public.third_party_identities;
create trigger tr_tpi_updated before update on public.third_party_identities
  for each row execute function public.set_updated_at();

create table if not exists public.account_identity_links (
  account_id uuid not null references public.accounts (id) on delete cascade,
  identity_id uuid not null references public.third_party_identities (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (account_id, identity_id)
);

create index if not exists idx_ail_identity on public.account_identity_links (identity_id);
create index if not exists idx_ail_account on public.account_identity_links (account_id);

alter table public.third_party_identities enable row level security;
alter table public.account_identity_links enable row level security;

-- third_party_identities
drop policy if exists tpi_select on public.third_party_identities;
create policy tpi_select on public.third_party_identities for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1
      from public.account_identity_links l
      join public.accounts a on a.id = l.account_id
      join public.technicians t on t.id = a.technician_id
      where l.identity_id = third_party_identities.id
        and t.auth_user_id = auth.uid()
    )
  )
);

drop policy if exists tpi_insert on public.third_party_identities;
create policy tpi_insert on public.third_party_identities for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists tpi_update on public.third_party_identities;
create policy tpi_update on public.third_party_identities for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists tpi_delete on public.third_party_identities;
create policy tpi_delete on public.third_party_identities for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

-- account_identity_links
drop policy if exists ail_select on public.account_identity_links;
create policy ail_select on public.account_identity_links for select to authenticated using (
  exists (
    select 1
    from public.accounts a
    where a.id = account_identity_links.account_id
      and (
        public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
        or (
          public.my_role() = 'tecnico'
          and exists (
            select 1
            from public.technicians t
            where t.auth_user_id = auth.uid() and t.id = a.technician_id
          )
        )
      )
  )
);

drop policy if exists ail_update on public.account_identity_links;

drop policy if exists ail_insert on public.account_identity_links;
create policy ail_insert on public.account_identity_links for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists ail_delete on public.account_identity_links;
create policy ail_delete on public.account_identity_links for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

-- Bucket privado para fotos de licencia (rutas: {identity_id}/front.ext)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'license-photos',
  'license-photos',
  false,
  5242880,
  array['image/jpeg', 'image/png', 'image/webp']::text[]
)
on conflict (id) do update set
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists lp_read on storage.objects;
create policy lp_read on storage.objects for select to authenticated using (
  bucket_id = 'license-photos'
  and (
    public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
    or (
      public.my_role() = 'tecnico'
      and split_part(name, '/', 1) in (
        select l.identity_id::text
        from public.account_identity_links l
        join public.accounts a on a.id = l.account_id
        join public.technicians t on t.id = a.technician_id
        where t.auth_user_id = auth.uid()
      )
    )
  )
);

drop policy if exists lp_insert on storage.objects;
create policy lp_insert on storage.objects for insert to authenticated with check (
  bucket_id = 'license-photos'
  and public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists lp_update on storage.objects;
create policy lp_update on storage.objects for update to authenticated using (
  bucket_id = 'license-photos'
  and public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
) with check (
  bucket_id = 'license-photos'
  and public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists lp_delete on storage.objects;
create policy lp_delete on storage.objects for delete to authenticated using (
  bucket_id = 'license-photos'
  and public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);
