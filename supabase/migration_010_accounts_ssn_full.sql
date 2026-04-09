-- Social/SSN completo en texto plano (no solo last4).
-- Ejecutar después de migration_009.

alter table public.accounts
  add column if not exists ssn_full text;

-- Si venís de la columna anterior ssn_last4, se migra a ssn_full con prefijo 'XXXXXX' para no inventar datos.
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'accounts' and column_name = 'ssn_last4'
  ) then
    update public.accounts
    set ssn_full = case
      when ssn_full is not null and length(trim(ssn_full)) > 0 then ssn_full
      when ssn_last4 is null then null
      else ('XXXXXX' || ssn_last4)
    end;

    alter table public.accounts drop constraint if exists chk_accounts_ssn_last4;
    alter table public.accounts drop column if exists ssn_last4;
  end if;
end $$;

comment on column public.accounts.ssn_full is
  'Social/SSN completo en texto plano (según proceso: conseguido por el equipo o provisto por el cliente).';

create index if not exists idx_accounts_ssn_full on public.accounts (ssn_full);

