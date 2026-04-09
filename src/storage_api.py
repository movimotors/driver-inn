"""Subida y descarga en Supabase Storage (JWT del usuario; respeta RLS del bucket)."""

from urllib.parse import quote

import httpx

from src.config import get_supabase_config

LICENSE_PHOTOS_BUCKET = "license-photos"


def _encode_object_path(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    return "/".join(quote(p, safe="") for p in parts)


def storage_upload(
    access_token: str,
    object_path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    url, anon = get_supabase_config()
    if not url or not anon:
        raise RuntimeError("Falta SUPABASE_URL o SUPABASE_KEY.")
    base = url.rstrip("/")
    enc = _encode_object_path(object_path)
    ep = f"{base}/storage/v1/object/{LICENSE_PHOTOS_BUCKET}/{enc}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": anon,
        "Content-Type": content_type,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(f"{ep}?upsert=true", headers=headers, content=data)
    if r.status_code not in (200, 201):
        raise RuntimeError(r.text or f"Upload HTTP {r.status_code}")


def storage_download(access_token: str, object_path: str) -> bytes:
    url, anon = get_supabase_config()
    if not url or not anon:
        raise RuntimeError("Falta SUPABASE_URL o SUPABASE_KEY.")
    base = url.rstrip("/")
    enc = _encode_object_path(object_path)
    ep = f"{base}/storage/v1/object/authenticated/{LICENSE_PHOTOS_BUCKET}/{enc}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": anon,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.get(ep, headers=headers)
    r.raise_for_status()
    return r.content


def storage_remove(access_token: str, object_path: str) -> None:
    url, anon = get_supabase_config()
    if not url or not anon:
        raise RuntimeError("Falta SUPABASE_URL o SUPABASE_KEY.")
    base = url.rstrip("/")
    enc = _encode_object_path(object_path)
    ep = f"{base}/storage/v1/object/{LICENSE_PHOTOS_BUCKET}/{enc}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": anon,
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.delete(ep, headers=headers)
    if r.status_code not in (200, 204):
        if r.status_code == 404:
            return
        raise RuntimeError(r.text or f"Delete HTTP {r.status_code}")
