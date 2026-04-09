"""Inventario y vínculo cuenta ↔ dato de tercero (modalidad cuenta a nombre de tercero)."""

from __future__ import annotations

TERCERO_MODALITY = "cuenta_nombre_tercero"


def links_by_identity(link_rows: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in link_rows or []:
        iid = row.get("identity_id")
        aid = row.get("account_id")
        if not iid or not aid:
            continue
        out.setdefault(str(iid), []).append(str(aid))
    return out


def links_by_account(link_rows: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in link_rows or []:
        iid = row.get("identity_id")
        aid = row.get("account_id")
        if not iid or not aid:
            continue
        out.setdefault(str(aid), []).append(str(iid))
    return out


def is_dato_malo(row: dict) -> bool:
    return row.get("data_semaphore") == "background_malo"


def inventory_bucket(row: dict, identity_id: str, links_map: dict[str, list[str]]) -> str:
    """malo | asignado | disponible"""
    if is_dato_malo(row):
        return "malo"
    accs = links_map.get(str(identity_id), [])
    return "asignado" if accs else "disponible"


def identity_option_label(row: dict) -> str:
    fn = (row.get("first_name") or "").strip()
    ln = (row.get("last_name") or "").strip()
    lic = (row.get("license_number") or "").strip() or "—"
    wf = (row.get("workflow_status") or "").replace("_", " ")
    return f"{fn} {ln}".strip() + f" · {lic}" + (f" · {wf}" if wf else "")


def identity_selectable_for_new_account(row: dict, iid: str, links_map: dict[str, list[str]]) -> bool:
    if is_dato_malo(row):
        return False
    return len(links_map.get(str(iid), [])) == 0


def identity_selectable_for_existing_account(
    row: dict, iid: str, links_map: dict[str, list[str]], account_id: str
) -> bool:
    if is_dato_malo(row):
        return False
    accs = links_map.get(str(iid), [])
    if not accs:
        return True
    return set(accs) == {str(account_id)}


def identity_rows_for_account_editor(
    rows: list[dict],
    links_map: dict[str, list[str]],
    account_id: str,
    current_identity_id: str | None,
) -> list[dict]:
    """Opciones de selector al editar cuenta: mantiene la ficha actual aunque quede bloqueada; el resto, reglas de inventario."""
    out: list[dict] = []
    cur = str(current_identity_id) if current_identity_id else None
    for row in rows:
        iid = str(row["id"])
        if cur and iid == cur:
            out.append(row)
            continue
        if identity_selectable_for_existing_account(row, iid, links_map, account_id):
            out.append(row)
    return out


def norm_license(value: str) -> str:
    return "".join(c for c in (value or "").strip().lower() if c.isalnum())


def validate_tercero_link(sb, account_id: str, identity_id: str) -> str | None:
    """
    No vincular si la cuenta ya tiene otra ficha con el mismo nº de licencia (misma lógica que Datos terceros).
    """
    ir = sb.table("third_party_identities").select("license_number,first_name,last_name").eq("id", identity_id).execute()
    if not ir.data:
        return "No se encontró el registro de datos de tercero."
    lic = ir.data[0].get("license_number") or ""
    target = norm_license(lic)
    if not target:
        return None

    lr = sb.table("account_identity_links").select("identity_id").eq("account_id", account_id).execute()
    for link in lr.data or []:
        oid = str(link["identity_id"])
        if oid == str(identity_id):
            continue
        other = (
            sb.table("third_party_identities")
            .select("license_number,first_name,last_name")
            .eq("id", oid)
            .execute()
        )
        if not other.data:
            continue
        o = other.data[0]
        if norm_license(o.get("license_number") or "") != target:
            continue
        lic_disp = (o.get("license_number") or "").strip() or "—"
        nom = f"{o.get('first_name', '')} {o.get('last_name', '')}".strip() or "otro registro"
        return (
            f"Esta cuenta ya tiene vinculada otra ficha con el **mismo número de licencia** "
            f"(`{lic_disp}`, {nom}). Quitá ese vínculo antes o elegí otro dato de tercero."
        )
    return None


def apply_account_tercero_identity(
    sb,
    account_id: str,
    service_modality: str,
    identity_id: str | None,
    client_face_photo_path: str | None = None,
) -> None:
    """Quita vínculos de la cuenta y, si aplica, crea el vínculo al dato de tercero."""
    sb.table("account_identity_links").delete().eq("account_id", account_id).execute()
    if service_modality == TERCERO_MODALITY and identity_id:
        row = {"account_id": account_id, "identity_id": identity_id}
        if client_face_photo_path:
            row["client_face_photo_path"] = client_face_photo_path
        sb.table("account_identity_links").insert(row).execute()


def current_tercero_identity_id(sb, account_id: str) -> str | None:
    r = sb.table("account_identity_links").select("identity_id").eq("account_id", account_id).execute()
    rows = r.data or []
    if not rows:
        return None
    return str(rows[0]["identity_id"])


def load_identities_and_links(sb) -> tuple[list[dict], dict[str, list[str]], dict[str, list[str]]]:
    tpi = (sb.table("third_party_identities").select("*").order("created_at", desc=True).execute().data) or []
    link_rows = (sb.table("account_identity_links").select("identity_id,account_id").execute().data) or []
    by_i = links_by_identity(link_rows)
    by_a = links_by_account(link_rows)
    return tpi, by_i, by_a
