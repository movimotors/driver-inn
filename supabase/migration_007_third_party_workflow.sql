-- Flujo solicitud → cliente → técnico, semáforo de calidad del dato (incl. Background malo) y Kanban.
-- Ejecutar después de migration_005.

do $$ begin
  create type public.tpi_data_semaphore as enum (
    'apto',
    'revisar',
    'background_malo'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.tpi_workflow_status as enum (
    'solicitud',
    'asignada',
    'en_proceso',
    'en_revision',
    'listo_cuentas',
    'cerrado'
  );
exception when duplicate_object then null;
end $$;

alter table public.third_party_identities
  add column if not exists request_client_id uuid references public.clients (id) on delete set null;

alter table public.third_party_identities
  add column if not exists assigned_technician_id uuid references public.technicians (id) on delete set null;

alter table public.third_party_identities
  add column if not exists data_semaphore public.tpi_data_semaphore not null default 'revisar';

alter table public.third_party_identities
  add column if not exists workflow_status public.tpi_workflow_status not null default 'solicitud';

create index if not exists idx_tpi_request_client on public.third_party_identities (request_client_id);
create index if not exists idx_tpi_assigned_tech on public.third_party_identities (assigned_technician_id);
create index if not exists idx_tpi_semaphore on public.third_party_identities (data_semaphore);
create index if not exists idx_tpi_workflow on public.third_party_identities (workflow_status);

-- No vincular cuentas si el dato está marcado Background malo
create or replace function public.prevent_link_if_dato_malo()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  sem public.tpi_data_semaphore;
begin
  select i.data_semaphore into sem
  from public.third_party_identities i
  where i.id = new.identity_id;
  if sem = 'background_malo' then
    raise exception 'Este dato está marcado como Background malo: no se puede asignar a cuentas.';
  end if;
  return new;
end;
$$;

drop trigger if exists tr_ail_no_malo on public.account_identity_links;
create trigger tr_ail_no_malo
  before insert on public.account_identity_links
  for each row execute function public.prevent_link_if_dato_malo();

-- RLS: técnico ve y actualiza filas asignadas por assigned_technician_id (además del vínculo vía cuentas)
drop policy if exists tpi_select on public.third_party_identities;
create policy tpi_select on public.third_party_identities for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1 from public.technicians t
      where t.auth_user_id = auth.uid()
        and t.id = third_party_identities.assigned_technician_id
    )
  )
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1 from public.account_identity_links l
      join public.accounts a on a.id = l.account_id
      join public.technicians t on t.id = a.technician_id
      where l.identity_id = third_party_identities.id
        and t.auth_user_id = auth.uid()
    )
  )
);

drop policy if exists tpi_update on public.third_party_identities;
create policy tpi_update on public.third_party_identities for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1 from public.technicians t
      where t.auth_user_id = auth.uid()
        and t.id = third_party_identities.assigned_technician_id
    )
  )
) with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1 from public.technicians t
      where t.auth_user_id = auth.uid()
        and t.id = third_party_identities.assigned_technician_id
    )
  )
);
