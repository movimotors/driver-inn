import sys
from datetime import date
from io import BytesIO
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.db import get_client
from src.rbac import can_delete_datos_terceros, can_edit_datos_terceros, require_login
from src.storage_api import storage_download, storage_remove, storage_upload

st.title("Datos terceros (licencias)")

if not supabase_configured():
    st.error("Configura Supabase.")
    st.stop()

require_login()
token = st.session_state.access_token
sb = get_client(token)
edit_ok = can_edit_datos_terceros()
delete_ok = can_delete_datos_terceros()

LICENSE_STATUS_OPTS = [
    ("vigente", "Vigente"),
    ("por_vencer", "Por vencer"),
    ("vencida", "Vencida"),
    ("suspendida", "Suspendida"),
    ("revocada", "Revocada / cancelada"),
    ("en_tramite", "En trámite"),
]
STATUS_KEYS = [x[0] for x in LICENSE_STATUS_OPTS]
STATUS_LABEL = dict(LICENSE_STATUS_OPTS)

PLATFORM_FIELDS = [
    ("use_doordash", "DoorDash"),
    ("use_instacart", "Instacart"),
    ("use_lyft", "Lyft Driver"),
    ("use_ubereats", "Uber Eats"),
    ("use_spark_driver", "Spark Driver"),
    ("use_amazon_flex", "Amazon Flex"),
    ("use_veho", "Veho"),
    ("use_other", "Otra plataforma"),
]


def _platform_labels_row(row: dict) -> str:
    parts = [lbl for key, lbl in PLATFORM_FIELDS if row.get(key)]
    return ", ".join(parts) if parts else "—"


@st.cache_data(ttl=30)
def load_identities(_token: str):
    c = get_client(_token)
    r = c.table("third_party_identities").select("*").order("created_at", desc=True).execute()
    return r.data or []


@st.cache_data(ttl=30)
def load_links_by_identity(_token: str):
    c = get_client(_token)
    r = c.table("account_identity_links").select("identity_id,account_id").execute()
    out: dict[str, list[str]] = {}
    for row in r.data or []:
        iid = row.get("identity_id")
        aid = row.get("account_id")
        if not iid or not aid:
            continue
        out.setdefault(str(iid), []).append(str(aid))
    return out


@st.cache_data(ttl=30)
def load_account_choices(_token: str):
    c = get_client(_token)
    acc = (c.table("accounts").select("id,client_id,platform_id").execute().data) or []
    clients = {x["id"]: x.get("name") for x in (c.table("clients").select("id,name").execute().data or [])}
    plats = {x["id"]: x for x in (c.table("delivery_platforms").select("id,name,code").execute().data or [])}
    choices = []
    for a in acc:
        cid = a.get("client_id")
        pid = a.get("platform_id")
        cn = clients.get(cid, "?")
        p = plats.get(pid, {})
        pl = p.get("name") or p.get("code") or "?"
        short = str(a["id"])[:8]
        choices.append((a["id"], f"{cn} · {pl} · …{short}"))
    return choices


def _show_license_photo(label: str, path: str | None):
    if not path:
        st.caption(f"{label}: sin archivo")
        return
    try:
        data = storage_download(token, path)
        st.caption(label)
        st.image(BytesIO(data), use_container_width=True)
    except Exception as e:
        st.warning(f"{label}: no se pudo mostrar ({e})")


def _sync_links(identity_id: str, account_ids: list):
    sb.table("account_identity_links").delete().eq("identity_id", identity_id).execute()
    if not account_ids:
        return
    rows = [{"identity_id": identity_id, "account_id": aid} for aid in account_ids]
    sb.table("account_identity_links").insert(rows).execute()


def _delete_photos_if_any(row: dict):
    for key in ("photo_front_path", "photo_back_path"):
        p = row.get(key)
        if p:
            try:
                storage_remove(token, p)
            except Exception:
                pass


def _payload_from_form(
    first_name: str,
    last_name: str,
    address: str,
    lic_num: str,
    lic_status: str,
    issuing_state: str,
    dob,
    issued,
    expires,
    notes: str,
    platforms: dict[str, bool],
) -> dict:
    return {
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "address_line": address.strip() or None,
        "license_number": lic_num.strip(),
        "license_status": lic_status,
        "license_issuing_state": issuing_state.strip() or None,
        "date_of_birth": dob.isoformat() if dob else None,
        "license_issued_date": issued.isoformat() if issued else None,
        "license_expiry_date": expires.isoformat() if expires else None,
        "notes": notes.strip() or None,
        **platforms,
    }


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

try:
    rows = load_identities(token)
    links_map = load_links_by_identity(token)
    acct_choices = load_account_choices(token)
except Exception as e:
    st.error(f"Error al cargar datos: {e}")
    st.info("¿Ejecutaste **migration_005_datos_terceros.sql** en Supabase y creaste el bucket **license-photos**?")
    st.stop()

acct_ids = [x[0] for x in acct_choices]
acct_label = dict(acct_choices)

st.caption(
    "Registro de licencias de conductor para uso en plataformas. Las fotos se guardan en Storage (**license-photos**). "
    "Vinculá las **cuentas delivery** donde aplicará esta identidad."
)

# --- Tabla resumen ---
summary = []
for r in rows:
    iid = str(r["id"])
    accs = links_map.get(iid, [])
    acc_lbl = ", ".join(acct_label.get(a, str(a)[:8]) for a in accs[:3])
    if len(accs) > 3:
        acc_lbl += f" (+{len(accs) - 3})"
    summary.append(
        {
            "Nombre": f"{r.get('first_name', '')} {r.get('last_name', '')}".strip(),
            "Nº licencia": r.get("license_number"),
            "Estado lic.": STATUS_LABEL.get(r.get("license_status"), r.get("license_status")),
            "Vence": str(r.get("license_expiry_date") or "")[:10],
            "Plataformas": _platform_labels_row(r),
            "Cuentas": acc_lbl or "—",
            "_id": iid,
        }
    )
st.subheader("Listado")
st.dataframe(
    [{k: v for k, v in s.items() if k != "_id"} for s in summary],
    use_container_width=True,
    hide_index=True,
)

# --- Detalle: fotos y cuentas ---
st.subheader("Detalle y fotos")
if not rows:
    st.info("Todavía no hay registros." + (" Usá el formulario de alta abajo." if edit_ok else ""))
else:
    by_id = {str(r["id"]): r for r in rows}
    pick = st.selectbox(
        "Ver registro",
        options=list(by_id.keys()),
        format_func=lambda i: f"{by_id[i].get('first_name')} {by_id[i].get('last_name')} — {by_id[i].get('license_number')}",
    )
    cur = by_id[pick]
    c1, c2 = st.columns(2)
    with c1:
        _show_license_photo("Frente", cur.get("photo_front_path"))
    with c2:
        _show_license_photo("Dorso", cur.get("photo_back_path"))
    st.markdown("**Cuentas asignadas**")
    la = links_map.get(pick, [])
    if la:
        for a in la:
            st.write(f"- {acct_label.get(a, a)}")
    else:
        st.caption("Ninguna cuenta vinculada.")

# --- Alta ---
if edit_ok:
    with st.expander("Alta de licencia / datos terceros", expanded=not rows):
        with st.form("new_id"):
            n_fn = st.text_input("Nombre *")
            n_ln = st.text_input("Apellido *")
            n_addr = st.text_area("Dirección")
            n_lic = st.text_input("Número de licencia *")
            n_st = st.selectbox("Estado de la licencia", options=STATUS_KEYS, format_func=lambda x: STATUS_LABEL[x])
            n_iss_st = st.text_input("Estado emisor (EE. UU., ej. FL, TX)", max_chars=4)
            n_dob = st.date_input("Fecha de nacimiento", value=None)
            n_iss_d = st.date_input("Fecha de emisión", value=None)
            n_exp = st.date_input("Fecha de expiración *", value=date.today())
            st.markdown("**Uso previsto en plataformas**")
            plat_vals = {}
            cols = st.columns(4)
            for i, (field, lbl) in enumerate(PLATFORM_FIELDS):
                with cols[i % 4]:
                    plat_vals[field] = st.checkbox(lbl, key=f"n_{field}")
            st.markdown("**Fotos** (JPEG / PNG / WebP, máx. recomendado 5 MB c/u)")
            up_f = st.file_uploader("Frente", type=["jpg", "jpeg", "png", "webp"], key="nf")
            up_b = st.file_uploader("Dorso", type=["jpg", "jpeg", "png", "webp"], key="nb")
            n_accounts = st.multiselect(
                "Cuentas donde se asignará",
                options=acct_ids,
                format_func=lambda x: acct_label.get(x, str(x)),
            )
            n_notes = st.text_area("Notas")
            sub = st.form_submit_button("Guardar", type="primary")
        if sub:
            if not n_fn.strip() or not n_ln.strip() or not n_lic.strip():
                st.error("Nombre, apellido y número de licencia son obligatorios.")
            elif not n_exp:
                st.error("Indicá fecha de expiración.")
            else:
                payload = _payload_from_form(
                    n_fn,
                    n_ln,
                    n_addr,
                    n_lic,
                    n_st,
                    n_iss_st,
                    n_dob,
                    n_iss_d,
                    n_exp,
                    n_notes,
                    plat_vals,
                )
                try:
                    ins = sb.table("third_party_identities").insert(payload).execute()
                    new_id = str(ins.data[0]["id"])
                    ext_f = "jpg"
                    if up_f:
                        ext_f = (up_f.name.rsplit(".", 1)[-1] if "." in up_f.name else "jpg").lower()
                        if ext_f == "jpeg":
                            ext_f = "jpg"
                        pf = f"{new_id}/front.{ext_f}"
                        storage_upload(token, pf, up_f.getvalue(), up_f.type or "image/jpeg")
                        sb.table("third_party_identities").update({"photo_front_path": pf}).eq("id", new_id).execute()
                    if up_b:
                        ext_b = (up_b.name.rsplit(".", 1)[-1] if "." in up_b.name else "jpg").lower()
                        if ext_b == "jpeg":
                            ext_b = "jpg"
                        pb = f"{new_id}/back.{ext_b}"
                        storage_upload(token, pb, up_b.getvalue(), up_b.type or "image/jpeg")
                        sb.table("third_party_identities").update({"photo_back_path": pb}).eq("id", new_id).execute()
                    _sync_links(new_id, [str(x) for x in n_accounts])
                    st.cache_data.clear()
                    st.success("Registro creado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

# --- Edición / baja ---
if edit_ok and rows:
    with st.expander("Editar o eliminar registro"):
        by_id = {str(r["id"]): r for r in rows}
        e_pick = st.selectbox(
            "Registro",
            options=list(by_id.keys()),
            format_func=lambda i: f"{by_id[i].get('first_name')} {by_id[i].get('last_name')} — {by_id[i].get('license_number')}",
            key="edit_pick",
        )
        cur = by_id[e_pick]
        try:
            st_ix = STATUS_KEYS.index(cur.get("license_status") or "vigente")
        except ValueError:
            st_ix = 0
        with st.form("upd_id"):
            u_fn = st.text_input("Nombre", value=cur.get("first_name") or "")
            u_ln = st.text_input("Apellido", value=cur.get("last_name") or "")
            u_addr = st.text_area("Dirección", value=cur.get("address_line") or "")
            u_lic = st.text_input("Número de licencia", value=cur.get("license_number") or "")
            u_st = st.selectbox(
                "Estado de la licencia",
                options=STATUS_KEYS,
                format_func=lambda x: STATUS_LABEL[x],
                index=st_ix,
            )
            u_iss_st = st.text_input(
                "Estado emisor (EE. UU.)",
                value=cur.get("license_issuing_state") or "",
                max_chars=4,
            )
            dob = cur.get("date_of_birth")
            isd = cur.get("license_issued_date")
            exp = cur.get("license_expiry_date")
            u_dob = st.date_input(
                "Fecha de nacimiento",
                value=date.fromisoformat(str(dob)[:10]) if dob else None,
            )
            u_isd = st.date_input(
                "Fecha de emisión",
                value=date.fromisoformat(str(isd)[:10]) if isd else None,
            )
            u_exp = st.date_input(
                "Fecha de expiración",
                value=date.fromisoformat(str(exp)[:10]) if exp else date.today(),
            )
            st.markdown("**Plataformas**")
            u_plat = {}
            cols = st.columns(4)
            for i, (field, lbl) in enumerate(PLATFORM_FIELDS):
                with cols[i % 4]:
                    u_plat[field] = st.checkbox(lbl, value=bool(cur.get(field)), key=f"u_{e_pick}_{field}")
            st.markdown("**Reemplazar fotos** (opcional)")
            u_f = st.file_uploader("Nuevo frente", type=["jpg", "jpeg", "png", "webp"], key="uf")
            u_b = st.file_uploader("Nuevo dorso", type=["jpg", "jpeg", "png", "webp"], key="ub")
            linked = links_map.get(e_pick, [])
            u_accounts = st.multiselect(
                "Cuentas asignadas",
                options=acct_ids,
                default=[x for x in linked if x in acct_ids],
                format_func=lambda x: acct_label.get(x, str(x)),
            )
            u_notes = st.text_area("Notas", value=cur.get("notes") or "")
            save = st.form_submit_button("Guardar cambios")
        if save:
            if not u_fn.strip() or not u_ln.strip() or not u_lic.strip():
                st.error("Nombre, apellido y número de licencia son obligatorios.")
            else:
                upd = _payload_from_form(
                    u_fn,
                    u_ln,
                    u_addr,
                    u_lic,
                    u_st,
                    u_iss_st,
                    u_dob,
                    u_isd,
                    u_exp,
                    u_notes,
                    u_plat,
                )
                try:
                    sb.table("third_party_identities").update(upd).eq("id", e_pick).execute()
                    if u_f:
                        ext = (u_f.name.rsplit(".", 1)[-1] if "." in u_f.name else "jpg").lower()
                        if ext == "jpeg":
                            ext = "jpg"
                        pf = f"{e_pick}/front.{ext}"
                        storage_upload(token, pf, u_f.getvalue(), u_f.type or "image/jpeg")
                        sb.table("third_party_identities").update({"photo_front_path": pf}).eq("id", e_pick).execute()
                    if u_b:
                        ext = (u_b.name.rsplit(".", 1)[-1] if "." in u_b.name else "jpg").lower()
                        if ext == "jpeg":
                            ext = "jpg"
                        pb = f"{e_pick}/back.{ext}"
                        storage_upload(token, pb, u_b.getvalue(), u_b.type or "image/jpeg")
                        sb.table("third_party_identities").update({"photo_back_path": pb}).eq("id", e_pick).execute()
                    _sync_links(e_pick, [str(x) for x in u_accounts])
                    st.cache_data.clear()
                    st.success("Actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        if delete_ok:
            if st.button("Eliminar registro y fotos", type="primary"):
                try:
                    _delete_photos_if_any(cur)
                    sb.table("third_party_identities").delete().eq("id", e_pick).execute()
                    st.cache_data.clear()
                    st.success("Eliminado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        else:
            st.caption("Solo **super usuario** o **administración** pueden eliminar registros.")

elif not edit_ok:
    st.info("Tu rol puede ver datos vinculados a tus cuentas asignadas (técnico) o todo el listado (vendedor). "
            "Alta y edición: **vendedor**, **administración** o **super usuario**.")
