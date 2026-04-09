-- Licencia del CLIENTE (para modalidades solo licencia / activación).
-- Campos equivalentes a third_party_identities, pero ligados 1:1 a la cuenta.
-- Ejecutar después de migration_010.

create table if not exists public.account_client_license_details (
  account_id uuid primary key references public.accounts (id) on delete cascade,
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
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists tr_acld_updated on public.account_client_license_details;
create trigger tr_acld_updated before update on public.account_client_license_details
  for each row execute function public.set_updated_at();

create index if not exists idx_acld_license_number on public.account_client_license_details (license_number);

alter table public.account_client_license_details enable row level security;

drop policy if exists acld_select on public.account_client_license_details;
create policy acld_select on public.account_client_license_details for select to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_client_license_details.account_id
      and (
        public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
        or (
          public.my_role() = 'tecnico'
          and exists (
            select 1 from public.technicians t
            where t.auth_user_id = auth.uid() and t.id = a.technician_id
          )
        )
      )
  )
);

drop policy if exists acld_insert on public.account_client_license_details;
create policy acld_insert on public.account_client_license_details for insert to authenticated with check (
  exists (
    select 1 from public.accounts a
    where a.id = account_client_license_details.account_id
      and (
        public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
        or (
          public.my_role() = 'tecnico'
          and exists (
            select 1 from public.technicians t
            where t.auth_user_id = auth.uid() and t.id = a.technician_id
          )
        )
      )
  )
);

drop policy if exists acld_update on public.account_client_license_details;
create policy acld_update on public.account_client_license_details for update to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_client_license_details.account_id
      and (
        public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
        or (
          public.my_role() = 'tecnico'
          and exists (
            select 1 from public.technicians t
            where t.auth_user_id = auth.uid() and t.id = a.technician_id
          )
        )
      )
  )
) with check (
  exists (
    select 1 from public.accounts a
    where a.id = account_client_license_details.account_id
      and (
        public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
        or (
          public.my_role() = 'tecnico'
          and exists (
            select 1 from public.technicians t
            where t.auth_user_id = auth.uid() and t.id = a.technician_id
          )
        )
      )
  )
);

drop policy if exists acld_delete on public.account_client_license_details;
create policy acld_delete on public.account_client_license_details for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

