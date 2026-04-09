"""Cuentas modalidad solo licencia (cliente_licencia_sin_social): registro aparte + fotos Storage."""

from __future__ import annotations

from src.storage_api import storage_remove

SOLO_LICENCIA_MODALITY = "cliente_licencia_sin_social"
TABLE = "account_solo_licencia_records"


def solo_table_available(sb) -> bool:
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
    e = ext.lower()
    return f"solo-licencia/{account_id}/front.{e}"


def back_storage_path(account_id: str, ext: str) -> str:
    e = ext.lower()
    return f"solo-licencia/{account_id}/back.{e}"


def _clean_ext(ext: str) -> str:
    e = (ext or "jpg").lower()
    if e == "jpeg":
        e = "jpg"
    return e if e in ("jpg", "png", "webp") else "jpg"


def storage_paths_for_account(account_id: str, front_ext: str, back_ext: str | None) -> tuple[str, str | None]:
    fe = _clean_ext(front_ext)
    front = front_storage_path(account_id, fe)
    if back_ext:
        be = _clean_ext(back_ext)
        return front, back_storage_path(account_id, be)
    return front, None


def fetch_solo_map(sb) -> dict[str, dict]:
    try:
        r = sb.table(TABLE).select("*").execute()
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for row in r.data or []:
        aid = row.get("account_id")
        if aid:
            out[str(aid)] = row
    return out


def delete_record(sb, account_id: str) -> None:
    sb.table(TABLE).delete().eq("account_id", account_id).execute()


def remove_storage_files(token: str, row: dict | None) -> None:
    if not row:
        return
    for key in ("photo_front_path", "photo_back_path"):
        p = row.get(key)
        if p:
            try:
                storage_remove(token, p)
            except Exception:
                pass


def upsert_solo_record(
    sb,
    account_id: str,
    sale_price: float,
    notes: str | None,
    photo_front_path: str | None,
    photo_back_path: str | None,
) -> None:
    ex = sb.table(TABLE).select("account_id").eq("account_id", account_id).execute()
    payload = {
        "sale_price": float(sale_price),
        "notes": (notes.strip() or None) if notes else None,
        "photo_front_path": photo_front_path,
        "photo_back_path": photo_back_path,
    }
    if ex.data:
        sb.table(TABLE).update(payload).eq("account_id", account_id).execute()
    else:
        sb.table(TABLE).insert({"account_id": account_id, **payload}).execute()
