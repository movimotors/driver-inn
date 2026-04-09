-- Esquema inicial: gestión de cuentas delivery (USA)
-- Ejecutar en Supabase SQL Editor o como migración.

-- Plataformas soportadas (semilla opcional al final)
create table if not exists public.delivery_platforms (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

-- Clientes (quien contrata / compra la cuenta)
create table if not exists public.clients (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text,
  phone text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Técnicos (quienes ejecutan / reciben la cuenta asignada)
create table if not exists public.technicians (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text,
  phone text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Tipos enum (idempotente si ya existen)
do $$ begin
  create type public.account_sale_type as enum ('venta', 'alquiler');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.account_status as enum (
    'solicitud',
    'asignada',
    'en_proceso',
    'requisitos_ok',
    'entregada',
    'suspendida',
    'cancelada'
  );
exception when duplicate_object then null;
end $$;

create table if not exists public.accounts (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.clients (id) on delete restrict,
  platform_id uuid not null references public.delivery_platforms (id) on delete restrict,
  technician_id uuid references public.technicians (id) on delete set null,
  sale_type public.account_sale_type not null default 'venta',
  status public.account_status not null default 'solicitud',
  requirements_checklist jsonb default '{}'::jsonb,
  requirements_notes text,
  assigned_at timestamptz,
  delivered_at timestamptz,
  -- Alquiler: monto semanal y próximo vencimiento
  rental_weekly_amount numeric(12, 2),
  rental_next_due_date date,
  rental_grace_days int default 0,
  external_ref text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_accounts_client on public.accounts (client_id);
create index if not exists idx_accounts_technician on public.accounts (technician_id);
create index if not exists idx_accounts_status on public.accounts (status);
create index if not exists idx_accounts_rental_due on public.accounts (rental_next_due_date)
  where sale_type = 'alquiler';

-- Pagos de alquiler (historial)
do $$ begin
  create type public.rental_payment_status as enum ('pendiente', 'pagado', 'atrasado');
exception when duplicate_object then null;
end $$;

create table if not exists public.rental_payments (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts (id) on delete cascade,
  period_label text,
  amount numeric(12, 2) not null,
  due_date date not null,
  paid_at timestamptz,
  status public.rental_payment_status not null default 'pendiente',
  notes text,
  created_at timestamptz not null default now()
);

create index if not exists idx_rental_payments_account on public.rental_payments (account_id);
create index if not exists idx_rental_payments_due on public.rental_payments (due_date);

-- Auditoría simple de cambios de estado
create table if not exists public.account_status_events (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts (id) on delete cascade,
  old_status public.account_status,
  new_status public.account_status not null,
  note text,
  created_at timestamptz not null default now()
);

-- updated_at automático
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists tr_clients_updated on public.clients;
create trigger tr_clients_updated before update on public.clients
  for each row execute function public.set_updated_at();

drop trigger if exists tr_technicians_updated on public.technicians;
create trigger tr_technicians_updated before update on public.technicians
  for each row execute function public.set_updated_at();

drop trigger if exists tr_accounts_updated on public.accounts;
create trigger tr_accounts_updated before update on public.accounts
  for each row execute function public.set_updated_at();

-- Semilla de plataformas
insert into public.delivery_platforms (code, name) values
  ('instacart', 'Instacart'),
  ('uber_eats', 'Uber Eats'),
  ('lyft', 'Lyft'),
  ('spark', 'Spark Driver'),
  ('amazon_flex', 'Amazon Flex'),
  ('veho', 'Veho'),
  ('doordash', 'DoorDash')
on conflict (code) do nothing;

-- RLS: habilitar; políticas abiertas solo para desarrollo (ajustar con auth real)
alter table public.delivery_platforms enable row level security;
alter table public.clients enable row level security;
alter table public.technicians enable row level security;
alter table public.accounts enable row level security;
alter table public.rental_payments enable row level security;
alter table public.account_status_events enable row level security;

-- Política permisiva (solo desarrollo; reemplazar con auth y roles en producción)
drop policy if exists dev_all_clients on public.clients;
create policy dev_all_clients on public.clients for all using (true) with check (true);
drop policy if exists dev_all_technicians on public.technicians;
create policy dev_all_technicians on public.technicians for all using (true) with check (true);
drop policy if exists dev_all_platforms on public.delivery_platforms;
create policy dev_all_platforms on public.delivery_platforms for all using (true) with check (true);
drop policy if exists dev_all_accounts on public.accounts;
create policy dev_all_accounts on public.accounts for all using (true) with check (true);
drop policy if exists dev_all_rental_payments on public.rental_payments;
create policy dev_all_rental_payments on public.rental_payments for all using (true) with check (true);
drop policy if exists dev_all_status_events on public.account_status_events;
create policy dev_all_status_events on public.account_status_events for all using (true) with check (true);
