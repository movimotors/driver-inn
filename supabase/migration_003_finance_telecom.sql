-- Migración 003: finanzas operativas + inventario telecom (datos, números, proxies, líneas)
-- Ejecutar en Supabase SQL Editor DESPUÉS de schema.sql y migration_002_auth_profiles_rls.sql
-- (Si ves error "set_updated_at does not exist", el bloque siguiente lo crea; también está en schema.sql)

-- Igual que en schema.sql: mantiene updated_at al hacer UPDATE
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Tipos
-- ---------------------------------------------------------------------------
do $$ begin
  create type public.finance_document_status as enum (
    'pendiente',
    'parcial',
    'pagado',
    'cobrado',
    'vencido',
    'cancelado'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.telecom_resource_type as enum (
    'datos',
    'numero_telefonico',
    'proxy',
    'linea_telefonica'
  );
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.telecom_resource_status as enum (
    'activo',
    'suspendido',
    'vencido',
    'reserva'
  );
exception when duplicate_object then null;
end $$;

-- ---------------------------------------------------------------------------
-- Cuentas por pagar (obligaciones con proveedores)
-- ---------------------------------------------------------------------------
create table if not exists public.accounts_payable (
  id uuid primary key default gen_random_uuid(),
  vendor_name text not null,
  category text,
  description text,
  amount numeric(14, 2) not null,
  currency text not null default 'USD',
  due_date date not null,
  paid_at timestamptz,
  paid_amount numeric(14, 2) not null default 0,
  status public.finance_document_status not null default 'pendiente',
  reference_number text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_payable_due on public.accounts_payable (due_date);
create index if not exists idx_payable_status on public.accounts_payable (status);
create index if not exists idx_payable_vendor on public.accounts_payable (vendor_name);

drop trigger if exists tr_accounts_payable_updated on public.accounts_payable;
create trigger tr_accounts_payable_updated before update on public.accounts_payable
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Cuentas por cobrar (cobros a clientes u otros deudores)
-- ---------------------------------------------------------------------------
create table if not exists public.accounts_receivable (
  id uuid primary key default gen_random_uuid(),
  client_id uuid references public.clients (id) on delete set null,
  counterparty_name text,
  description text,
  amount numeric(14, 2) not null,
  currency text not null default 'USD',
  due_date date not null,
  received_at timestamptz,
  received_amount numeric(14, 2) not null default 0,
  status public.finance_document_status not null default 'pendiente',
  reference_number text,
  related_delivery_account_id uuid references public.accounts (id) on delete set null,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint accounts_receivable_party_chk check (client_id is not null or counterparty_name is not null)
);

create index if not exists idx_receivable_due on public.accounts_receivable (due_date);
create index if not exists idx_receivable_status on public.accounts_receivable (status);
create index if not exists idx_receivable_client on public.accounts_receivable (client_id);

drop trigger if exists tr_accounts_receivable_updated on public.accounts_receivable;
create trigger tr_accounts_receivable_updated before update on public.accounts_receivable
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Gastos operativos
-- ---------------------------------------------------------------------------
create table if not exists public.operational_expenses (
  id uuid primary key default gen_random_uuid(),
  category text not null,
  vendor_name text,
  description text,
  amount numeric(14, 2) not null,
  currency text not null default 'USD',
  expense_date date not null default (current_date),
  payment_method text,
  receipt_ref text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_opex_date on public.operational_expenses (expense_date);
create index if not exists idx_opex_category on public.operational_expenses (category);

drop trigger if exists tr_operational_expenses_updated on public.operational_expenses;
create trigger tr_operational_expenses_updated before update on public.operational_expenses
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Inventario / inversiones telecom: planes de datos, números, proxies, líneas
-- ---------------------------------------------------------------------------
create table if not exists public.telecom_resources (
  id uuid primary key default gen_random_uuid(),
  resource_type public.telecom_resource_type not null,
  label text not null,
  provider text,
  identifier text,
  credentials_vault_ref text,
  monthly_cost numeric(14, 2),
  initial_investment numeric(14, 2),
  start_date date,
  renewal_date date,
  status public.telecom_resource_status not null default 'activo',
  technician_id uuid references public.technicians (id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_telecom_type on public.telecom_resources (resource_type);
create index if not exists idx_telecom_status on public.telecom_resources (status);
create index if not exists idx_telecom_tech on public.telecom_resources (technician_id);
create index if not exists idx_telecom_renewal on public.telecom_resources (renewal_date);

drop trigger if exists tr_telecom_resources_updated on public.telecom_resources;
create trigger tr_telecom_resources_updated before update on public.telecom_resources
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- RLS (misma filosofía que migration_002: helpers has_any_role / my_role)
-- Finanzas: sin acceso para rol técnico. Telecom: técnico solo filas asignadas (lectura).
-- ---------------------------------------------------------------------------
alter table public.accounts_payable enable row level security;
alter table public.accounts_receivable enable row level security;
alter table public.operational_expenses enable row level security;
alter table public.telecom_resources enable row level security;

-- accounts_payable
drop policy if exists ap_select on public.accounts_payable;
create policy ap_select on public.accounts_payable for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists ap_insert on public.accounts_payable;
create policy ap_insert on public.accounts_payable for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists ap_update on public.accounts_payable;
create policy ap_update on public.accounts_payable for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists ap_delete on public.accounts_payable;
create policy ap_delete on public.accounts_payable for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

-- accounts_receivable
drop policy if exists ar_select on public.accounts_receivable;
create policy ar_select on public.accounts_receivable for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists ar_insert on public.accounts_receivable;
create policy ar_insert on public.accounts_receivable for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists ar_update on public.accounts_receivable;
create policy ar_update on public.accounts_receivable for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists ar_delete on public.accounts_receivable;
create policy ar_delete on public.accounts_receivable for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

-- operational_expenses
drop policy if exists opex_select on public.operational_expenses;
create policy opex_select on public.operational_expenses for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists opex_insert on public.operational_expenses;
create policy opex_insert on public.operational_expenses for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists opex_update on public.operational_expenses;
create policy opex_update on public.operational_expenses for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists opex_delete on public.operational_expenses;
create policy opex_delete on public.operational_expenses for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

-- telecom_resources
drop policy if exists tr_res_select on public.telecom_resources;
create policy tr_res_select on public.telecom_resources for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1
      from public.technicians t
      where t.auth_user_id = auth.uid() and t.id = telecom_resources.technician_id
    )
  )
);

drop policy if exists tr_res_insert on public.telecom_resources;
create policy tr_res_insert on public.telecom_resources for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

drop policy if exists tr_res_update on public.telecom_resources;
create policy tr_res_update on public.telecom_resources for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

drop policy if exists tr_res_delete on public.telecom_resources;
create policy tr_res_delete on public.telecom_resources for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

-- ---------------------------------------------------------------------------
-- Datos de ejemplo (INSERT). Ajustá o borrá tras probar.
-- ---------------------------------------------------------------------------

-- Cuentas por pagar
insert into public.accounts_payable (
  vendor_name, category, description, amount, currency, due_date, paid_amount, status, reference_number, notes
) values
  ('Twilio', 'Telecom', 'Recarga / uso mensual API SMS', 120.50, 'USD', current_date + 10, 0, 'pendiente', 'TW-2026-04', 'Pagar con tarjeta corporativa'),
  ('ProxyMesh', 'Infra', 'Suscripción proxies residenciales', 79.00, 'USD', current_date - 2, 0, 'vencido', 'PM-4412', 'Renovar o migrar proveedor'),
  ('AT&T Business', 'Telecom', 'Línea dedicada oficina', 210.00, 'USD', current_date + 25, 210.00, 'pagado', 'ATT-778', 'Ya liquidado; dejar como historial');

-- Cuentas por cobrar (con cliente si existe alguno; si no, solo contraparte por nombre)
insert into public.accounts_receivable (
  client_id, counterparty_name, description, amount, currency, due_date, received_amount, status, reference_number, notes
)
select
  c.id,
  null,
  'Saldo instalación cuenta delivery + primer mes',
  450.00,
  'USD',
  current_date + 7,
  0,
  'pendiente',
  'CX-1001',
  'Generado automáticamente de ejemplo'
from public.clients c
order by c.created_at
limit 1;

insert into public.accounts_receivable (
  client_id, counterparty_name, description, amount, currency, due_date, received_amount, status, reference_number, notes
) values (
  null,
  'Cliente externo Demo',
  'Cuota semanal alquiler plataforma',
  85.00,
  'USD',
  current_date + 3,
  40.00,
  'parcial',
  'CX-EXT-02',
  'Ejemplo sin vínculo a tabla clients'
);

-- Gastos operativos
insert into public.operational_expenses (
  category, vendor_name, description, amount, currency, expense_date, payment_method, receipt_ref, notes
) values
  ('Oficina', 'Staples', 'Consumibles impresión', 42.30, 'USD', current_date - 5, 'tarjeta', 'RCP-ST-992', null),
  ('Software', 'Google Workspace', 'Licencias correo', 72.00, 'USD', current_date - 1, 'transferencia', 'INV-GWS-04', 'Factura mensual'),
  ('Legal', 'Estudio Demo LLC', 'Revisión contrato estándar', 350.00, 'USD', current_date - 12, 'transferencia', 'LEG-2026-01', null);

-- Telecom: plan de datos (asigna primer técnico activo si existe)
insert into public.telecom_resources (
  resource_type, label, provider, identifier, credentials_vault_ref, monthly_cost, initial_investment,
  start_date, renewal_date, status, technician_id, metadata, notes
)
select
  'datos'::public.telecom_resource_type,
  'Plan datos móvil operaciones',
  'T-Mobile',
  'eSIM / ICCID ****9012',
  'vault/kv/tmobile_ops_01',
  55.00,
  15.00,
  current_date - 60,
  current_date + 30,
  'activo'::public.telecom_resource_status,
  (select t.id from public.technicians t where t.active = true order by t.created_at asc limit 1),
  '{"apn":"fast.t-mobile.com","cap_gb":50}'::jsonb,
  'No guardar secretos en texto plano; usar credentials_vault_ref';

-- Número, proxy y línea (ejemplos fijos)
insert into public.telecom_resources (
  resource_type, label, provider, identifier, credentials_vault_ref, monthly_cost, initial_investment,
  start_date, renewal_date, status, technician_id, metadata, notes
) values
  (
    'numero_telefonico',
    'Número verificación SMS',
    'Bandwidth',
    '+1 (555) 010-0199',
    null,
    3.50,
    2.00,
    current_date - 20,
    null,
    'activo',
    null,
    '{"uso":"OTP","pais":"US"}'::jsonb,
    'Número de ejemplo; reemplazar en producción'
  ),
  (
    'proxy',
    'Proxy residencial US-East',
    'Bright Data',
    'gate.brd.superproxy.io:22225',
    'vault/kv/bd_user_main',
    99.00,
    0,
    current_date - 10,
    current_date + 20,
    'activo',
    null,
    '{"zona":"us-east-1"}'::jsonb,
    'Rotación cada solicitud'
  ),
  (
    'linea_telefonica',
    'Línea soporte cuentas',
    'RingCentral',
    'Ext 1200 / DID +1-555-0100',
    null,
    45.00,
    25.00,
    current_date - 90,
    current_date + 45,
    'activo',
    null,
    '{"minutos_incluidos":500}'::jsonb,
    'Línea VOIP central'
  );

-- Fin migración 003
