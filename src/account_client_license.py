"""Licencia del cliente por cuenta (modalidades solo licencia / activación)."""

from __future__ import annotations

TABLE = "account_client_license_details"


def table_available(sb) -> bool:
    try:
        sb.table(TABLE).select("account_id").limit(1).execute()
        return True
    except Exception:
        return False


def normalize_image_ext(filename: str) -> str:
    e = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    if e == "jpeg":
        e = "jpg"
    return e if e in ("jpg", "png", "webp") else "jpg"


def front_storage_path(account_id: str, ext: str) -> str:
    return f"cliente-licencia/{account_id}/front.{ext.lower()}"


def back_storage_path(account_id: str, ext: str) -> str:
    return f"cliente-licencia/{account_id}/back.{ext.lower()}"


def fetch_one(sb, account_id: str) -> dict | None:
    r = sb.table(TABLE).select("*").eq("account_id", account_id).execute()
    rows = r.data or []
    return rows[0] if rows else None


def upsert(sb, payload: dict) -> None:
    aid = payload.get("account_id")
    if not aid:
        raise RuntimeError("Falta account_id en payload.")
    ex = sb.table(TABLE).select("account_id").eq("account_id", aid).execute()
    if ex.data:
        sb.table(TABLE).update(payload).eq("account_id", aid).execute()
    else:
        sb.table(TABLE).insert(payload).execute()

