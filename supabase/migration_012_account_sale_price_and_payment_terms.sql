-- Venta: monto de venta + términos de pago (contado/crédito).
-- Ejecutar después de schema.sql

do $$ begin
  create type public.account_payment_terms as enum ('contado', 'credito');
exception when duplicate_object then null;
end $$;

alter table public.accounts
  add column if not exists sale_price numeric(12, 2);

alter table public.accounts
  add column if not exists payment_terms public.account_payment_terms;

comment on column public.accounts.sale_price is
  'Monto de venta cuando sale_type=venta.';

comment on column public.accounts.payment_terms is
  'Términos de pago cuando sale_type=venta (contado/crédito).';

create index if not exists idx_accounts_sale_price on public.accounts (sale_price);
create index if not exists idx_accounts_payment_terms on public.accounts (payment_terms);

