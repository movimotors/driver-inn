-- Cliente: modalidad por defecto. Cuenta: control de social/OK entrega.
-- Ejecución técnica: teléfono, correo y credenciales (tabla separada con RLS).
-- Ejecutar después de migration_006 y (si usas) migration_008.

-- 1) Default de modalidad en cliente
alter table public.clients
  add column if not exists default_service_modality public.account_service_modality
  not null default 'cuenta_nombre_tercero';

create index if not exists idx_clients_default_modality
  on public.clients (default_service_modality);

comment on column public.clients.default_service_modality is
  'Modalidad por defecto del cliente (se sugiere al crear cuentas).';

-- 2) Campos operativos en cuenta
alter table public.accounts
  add column if not exists social_obtained boolean not null default false;

alter table public.accounts
  add column if not exists ssn_last4 text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'chk_accounts_ssn_last4'
  ) then
    alter table public.accounts
      add constraint chk_accounts_ssn_last4
      check (ssn_last4 is null or ssn_last4 ~ '^[0-9]{4}$');
  end if;
end $$;

alter table public.accounts
  add column if not exists quality_ok boolean not null default false;

create index if not exists idx_accounts_quality_ok on public.accounts (quality_ok);
create index if not exists idx_accounts_social_obtained on public.accounts (social_obtained);

-- 3) Ejecución técnica (no passwords)
do $$ begin
  create type public.account_phone_source as enum (
    'cliente',
    'comprado_web',
    'otro'
  );
exception when duplicate_object then null;
end $$;

create table if not exists public.account_execution_details (
  account_id uuid primary key references public.accounts (id) on delete cascade,
  phone_number text,
  phone_source public.account_phone_source,
  email_created text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists tr_account_execution_details_updated on public.account_execution_details;
create trigger tr_account_execution_details_updated
  before update on public.account_execution_details
  for each row execute function public.set_updated_at();

create index if not exists idx_aed_phone_source on public.account_execution_details (phone_source);

alter table public.account_execution_details enable row level security;

drop policy if exists aed_select on public.account_execution_details;
create policy aed_select on public.account_execution_details for select to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_execution_details.account_id
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

drop policy if exists aed_insert on public.account_execution_details;
create policy aed_insert on public.account_execution_details for insert to authenticated with check (
  exists (
    select 1 from public.accounts a
    where a.id = account_execution_details.account_id
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

drop policy if exists aed_update on public.account_execution_details;
create policy aed_update on public.account_execution_details for update to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_execution_details.account_id
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
    where a.id = account_execution_details.account_id
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

drop policy if exists aed_delete on public.account_execution_details;
create policy aed_delete on public.account_execution_details for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

-- 4) Credenciales (passwords) en tabla separada con RLS
-- IMPORTANTE: esto guarda texto plano. Recomendado: gestionar passwords en un password manager.
create table if not exists public.account_credentials (
  account_id uuid primary key references public.accounts (id) on delete cascade,
  email_login text,
  email_password text,
  app_password text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists tr_account_credentials_updated on public.account_credentials;
create trigger tr_account_credentials_updated
  before update on public.account_credentials
  for each row execute function public.set_updated_at();

alter table public.account_credentials enable row level security;

drop policy if exists ac_select on public.account_credentials;
create policy ac_select on public.account_credentials for select to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_credentials.account_id
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

drop policy if exists ac_insert on public.account_credentials;
create policy ac_insert on public.account_credentials for insert to authenticated with check (
  exists (
    select 1 from public.accounts a
    where a.id = account_credentials.account_id
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

drop policy if exists ac_update on public.account_credentials;
create policy ac_update on public.account_credentials for update to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_credentials.account_id
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
    where a.id = account_credentials.account_id
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

drop policy if exists ac_delete on public.account_credentials;
create policy ac_delete on public.account_credentials for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

