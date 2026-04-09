-- Registro aparte para cuentas modalidad "solo licencia" (cliente con licencia sin social):
-- foto(s) de licencia en Storage (rutas aquí) y precio de venta.
-- Ejecutar después de migration_006.

create table if not exists public.account_solo_licencia_records (
  account_id uuid primary key references public.accounts (id) on delete cascade,
  photo_front_path text,
  photo_back_path text,
  sale_price numeric(12, 2) not null default 0,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.account_solo_licencia_records is
  'Una fila por cuenta con modalidad cliente_licencia_sin_social: evidencia de licencia y precio cobrado.';

drop trigger if exists tr_account_solo_licencia_updated on public.account_solo_licencia_records;
create trigger tr_account_solo_licencia_updated
  before update on public.account_solo_licencia_records
  for each row execute function public.set_updated_at();

create index if not exists idx_account_solo_licencia_sale_price on public.account_solo_licencia_records (sale_price);

alter table public.account_solo_licencia_records enable row level security;

drop policy if exists aslr_select on public.account_solo_licencia_records;
create policy aslr_select on public.account_solo_licencia_records for select to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_solo_licencia_records.account_id
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

drop policy if exists aslr_insert on public.account_solo_licencia_records;
create policy aslr_insert on public.account_solo_licencia_records for insert to authenticated with check (
  exists (
    select 1 from public.accounts a
    where a.id = account_solo_licencia_records.account_id
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

drop policy if exists aslr_update on public.account_solo_licencia_records;
create policy aslr_update on public.account_solo_licencia_records for update to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_solo_licencia_records.account_id
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
    where a.id = account_solo_licencia_records.account_id
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

drop policy if exists aslr_delete on public.account_solo_licencia_records;
create policy aslr_delete on public.account_solo_licencia_records for delete to authenticated using (
  exists (
    select 1 from public.accounts a
    where a.id = account_solo_licencia_records.account_id
      and public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  )
);
