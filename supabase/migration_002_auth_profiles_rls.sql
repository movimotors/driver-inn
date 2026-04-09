-- Auth: perfiles, roles y RLS (ejecutar después de schema.sql en Supabase SQL Editor)
-- Requiere extensión pgcrypto (gen_random_uuid) ya usada en schema base.
-- Si falla "set_updated_at does not exist", ejecutá primero schema.sql o este bloque:

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- Rol de aplicación
do $$ begin
  create type public.app_user_role as enum (
    'superusuario',
    'administracion',
    'vendedor',
    'tecnico'
  );
exception when duplicate_object then null;
end $$;

-- Vincular técnico a usuario de Auth (opcional, para filtrar cuentas del técnico)
alter table public.technicians
  add column if not exists auth_user_id uuid unique references auth.users (id) on delete set null;

create index if not exists idx_technicians_auth_user on public.technicians (auth_user_id);

-- Perfil por usuario
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  full_name text,
  role public.app_user_role not null default 'tecnico',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists tr_profiles_updated on public.profiles;
create trigger tr_profiles_updated before update on public.profiles
  for each row execute function public.set_updated_at();

alter table public.profiles enable row level security;

-- Al crear usuario en Auth, crear fila en profiles
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, full_name, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
    'tecnico'
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Helpers RLS (evitan recursión al leer profiles)
create or replace function public.is_staff()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role in ('superusuario', 'administracion')
  );
$$;

create or replace function public.my_role()
returns public.app_user_role
language sql
stable
security definer
set search_path = public
as $$
  select p.role from public.profiles p where p.id = auth.uid();
$$;

create or replace function public.has_any_role(roles public.app_user_role[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.role = any (roles)
  );
$$;

-- Impedir que administración cree o edite superusuarios (lógica extra)
create or replace function public.enforce_profile_role_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  actor public.app_user_role;
begin
  if old.role is not distinct from new.role then
    return new;
  end if;
  select p.role into actor from public.profiles p where p.id = auth.uid();
  if actor is null then
    return new;
  end if;
  if actor = 'administracion' and new.role = 'superusuario' then
    raise exception 'Solo un super usuario puede asignar el rol superusuario';
  end if;
  if actor = 'administracion' and old.role = 'superusuario' then
    raise exception 'No autorizado a modificar un super usuario';
  end if;
  return new;
end;
$$;

drop trigger if exists tr_profiles_role_guard on public.profiles;
create trigger tr_profiles_role_guard
  before update on public.profiles
  for each row
  execute function public.enforce_profile_role_change();

-- Quitar políticas abiertas de desarrollo
drop policy if exists dev_all_clients on public.clients;
drop policy if exists dev_all_technicians on public.technicians;
drop policy if exists dev_all_platforms on public.delivery_platforms;
drop policy if exists dev_all_accounts on public.accounts;
drop policy if exists dev_all_rental_payments on public.rental_payments;
drop policy if exists dev_all_status_events on public.account_status_events;

-- profiles
drop policy if exists prof_select on public.profiles;
create policy prof_select on public.profiles for select to authenticated using (
  id = auth.uid() or public.is_staff()
);

drop policy if exists prof_update on public.profiles;
create policy prof_update on public.profiles for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

-- delivery_platforms
drop policy if exists dp_select on public.delivery_platforms;
create policy dp_select on public.delivery_platforms for select to authenticated using (true);

-- clients
drop policy if exists clients_select on public.clients;
create policy clients_select on public.clients for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor', 'tecnico']::public.app_user_role[])
);

drop policy if exists clients_insert on public.clients;
create policy clients_insert on public.clients for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists clients_update on public.clients;
create policy clients_update on public.clients for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

-- technicians
drop policy if exists tech_select on public.technicians;
create policy tech_select on public.technicians for select to authenticated using (true);

drop policy if exists tech_insert on public.technicians;
create policy tech_insert on public.technicians for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

drop policy if exists tech_update on public.technicians;
create policy tech_update on public.technicians for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

drop policy if exists tech_delete on public.technicians;
create policy tech_delete on public.technicians for delete to authenticated using (
  public.has_any_role (array['superusuario', 'administracion']::public.app_user_role[])
);

-- accounts
drop policy if exists accounts_select on public.accounts;
create policy accounts_select on public.accounts for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1
      from public.technicians t
      where t.auth_user_id = auth.uid() and t.id = accounts.technician_id
    )
  )
);

drop policy if exists accounts_insert on public.accounts;
create policy accounts_insert on public.accounts for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists accounts_update on public.accounts;
create policy accounts_update on public.accounts for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1
      from public.technicians t
      where t.auth_user_id = auth.uid() and t.id = accounts.technician_id
    )
  )
) with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1
      from public.technicians t
      where t.auth_user_id = auth.uid() and t.id = accounts.technician_id
    )
  )
);

-- rental_payments (técnicos no gestionan cobros aquí)
drop policy if exists rp_select on public.rental_payments;
create policy rp_select on public.rental_payments for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists rp_insert on public.rental_payments;
create policy rp_insert on public.rental_payments for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

drop policy if exists rp_update on public.rental_payments;
create policy rp_update on public.rental_payments for update to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
) with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
);

-- account_status_events
drop policy if exists ase_select on public.account_status_events;
create policy ase_select on public.account_status_events for select to authenticated using (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1
      from public.accounts a
      join public.technicians t on t.id = a.technician_id
      where a.id = account_status_events.account_id and t.auth_user_id = auth.uid()
    )
  )
);

drop policy if exists ase_insert on public.account_status_events;
create policy ase_insert on public.account_status_events for insert to authenticated with check (
  public.has_any_role (array['superusuario', 'administracion', 'vendedor']::public.app_user_role[])
  or (
    public.my_role() = 'tecnico'
    and exists (
      select 1
      from public.accounts a
      join public.technicians t on t.id = a.technician_id
      where a.id = account_status_events.account_id and t.auth_user_id = auth.uid()
    )
  )
);

-- Primer super usuario: tras crear el usuario en Authentication, ejecutar:
-- update public.profiles set role = 'superusuario' where id = '<uuid del usuario>';
