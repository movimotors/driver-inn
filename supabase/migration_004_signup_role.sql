-- Rol elegido en el registro (metadata signup_role) y perfil inicial seguro.
-- Ejecutar en SQL Editor después de migration_002 (y 003 si aplica).
-- Solo acepta vendedor o tecnico desde metadata; nunca superusuario ni administracion.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  raw text;
  chosen public.app_user_role;
begin
  raw := lower(trim(coalesce(new.raw_user_meta_data->>'signup_role', '')));

  if raw = 'vendedor' then
    chosen := 'vendedor'::public.app_user_role;
  elsif raw in ('tecnico', 'técnico') then
    chosen := 'tecnico'::public.app_user_role;
  else
    -- Invitaciones / usuarios creados desde el panel sin rol: técnico por defecto (como antes).
    chosen := 'tecnico'::public.app_user_role;
  end if;

  insert into public.profiles (id, email, full_name, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
    chosen
  );
  return new;
end;
$$;
