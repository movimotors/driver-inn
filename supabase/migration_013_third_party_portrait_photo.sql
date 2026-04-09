-- Datos terceros: foto tipo carnet (frente) para validar identidad.
-- Ejecutar después de migration_005.

alter table public.third_party_identities
  add column if not exists portrait_photo_path text;

create index if not exists idx_tpi_portrait_photo on public.third_party_identities (portrait_photo_path);

comment on column public.third_party_identities.portrait_photo_path is
  'Foto tipo carnet (frente) del tercero (no reemplaza fotos de licencia).';

