-- Modalidad de servicio por cuenta delivery (cómo se crea / qué aporta el cliente).
-- Ejecutar en SQL Editor después de schema + migraciones anteriores.

do $$ begin
  create type public.account_service_modality as enum (
    'cuenta_nombre_tercero',
    'cliente_licencia_sin_social',
    'cliente_licencia_social_activacion_cupo'
  );
exception when duplicate_object then null;
end $$;

alter table public.accounts
  add column if not exists service_modality public.account_service_modality
  not null default 'cuenta_nombre_tercero';

comment on column public.accounts.service_modality is
  'cuenta_nombre_tercero: cuenta a nombre de tercero (datos terceros). '
  'cliente_licencia_sin_social: cliente ya tiene licencia, falta social/SSN. '
  'cliente_licencia_social_activacion_cupo: licencia + SSN; falta activación por cupo.';

create index if not exists idx_accounts_service_modality on public.accounts (service_modality);
