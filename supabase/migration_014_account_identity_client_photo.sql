-- Al asignar un dato de tercero a una cuenta: guardar foto del CLIENTE solicitante.
-- Ejecutar después de migration_005.

alter table public.account_identity_links
  add column if not exists client_face_photo_path text;

create index if not exists idx_ail_client_face on public.account_identity_links (client_face_photo_path);

comment on column public.account_identity_links.client_face_photo_path is
  'Foto del cliente solicitante (rostro) asociada al uso de un dato de tercero en una cuenta.';

