import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.constants import (
    ACCOUNT_STATUS_LABELS,
    ACCOUNT_STATUS_ORDER,
    SERVICE_MODALITY_HELP,
    SERVICE_MODALITY_LABELS,
    SERVICE_MODALITY_ORDER,
)
from src.account_solo_licencia import (
    SOLO_LICENCIA_MODALITY,
    back_storage_path,
    normalize_image_ext,
    solo_table_available,
    storage_paths_for_account,
    upsert_solo_record,
)
from src.db import fetch_accounts_list_with_modality_fallback, get_client
from src.rbac import ROLE_ADMIN, ROLE_SUPER, ROLE_VENDEDOR, require_roles
from src.storage_api import storage_upload
from src.tpi_account_linking import (
    TERCERO_MODALITY,
    apply_account_tercero_identity,
    identity_option_label,
    identity_selectable_for_new_account,
    load_identities_and_links,
    validate_tercero_link,
)

st.title("Clientes")

if not supabase_configured():
    st.error("Configura `.env` con Supabase.")
    st.stop()

require_roles([ROLE_SUPER, ROLE_ADMIN, ROLE_VENDEDOR])

token = st.session_state.access_token
sb = get_client(token)


@st.cache_data(ttl=30)
def list_clients(_token: str):
    c = get_client(_token)
    r = c.table("clients").select("*").order("created_at", desc=True).execute()
    return r.data or []


@st.cache_data(ttl=30)
def load_techs_plats(_token: str):
    c = get_client(_token)
    techs = (c.table("technicians").select("id,name,active").eq("active", True).order("name").execute().data) or []
    plats = (c.table("delivery_platforms").select("id,name,code").eq("active", True).order("name").execute().data) or []
    return techs, plats


@st.cache_data(ttl=30)
def load_accounts_schema(_token: str):
    return fetch_accounts_list_with_modality_fallback(get_client(_token))


if st.button("Refrescar lista"):
    st.cache_data.clear()
    st.rerun()

rows = list_clients(token)
st.dataframe(rows, use_container_width=True, hide_index=True)

cid = {c["id"]: c.get("name") for c in rows}
client_default_mod = {str(c["id"]): c.get("default_service_modality") for c in rows if c.get("id")}

try:
    techs, plats = load_techs_plats(token)
    _, schema_has_service_modality = load_accounts_schema(token)
    tpi_rows, links_by_i, _ = load_identities_and_links(sb)
except Exception:
    techs, plats = [], []
    schema_has_service_modality = False
    tpi_rows, links_by_i = [], {}
schema_has_solo_licencia = solo_table_available(sb)
tpi_by_id = {str(r["id"]): r for r in tpi_rows}
tid = {t["id"]: t["name"] for t in techs}
pid = {p["id"]: p["name"] for p in plats}
STATUS_OPTIONS = [(s, ACCOUNT_STATUS_LABELS[s]) for s in ACCOUNT_STATUS_ORDER]
SALE_OPTIONS = [("venta", "Venta"), ("alquiler", "Alquiler")]

with st.expander("Nueva cuenta delivery (cliente + inventario datos tercero)", expanded=False):
    st.markdown(
        "Creá la **cuenta** ya asociada al cliente elegido. Si la modalidad es **Cuenta a nombre de tercero**, "
        "elegí una ficha **disponible** del inventario (la misma lógica que en **Cuentas**)."
    )
    if not rows or not plats:
        st.warning("Necesitás al menos un **cliente** (arriba) y **plataformas** cargadas en el sistema.")
    else:
        pre_client = st.selectbox(
            "Cliente de la nueva cuenta",
            options=[c["id"] for c in rows],
            format_func=lambda x: cid.get(x, str(x)),
            key="cl_pre_client",
        )
        with st.form("cl_new_delivery_account"):
            platform_id = st.selectbox(
                "Plataforma",
                options=[p["id"] for p in plats],
                format_func=lambda x: pid.get(x, str(x)),
                key="cl_na_p",
            )
            default_mod = client_default_mod.get(str(pre_client)) or "cuenta_nombre_tercero"
            try:
                default_ix = SERVICE_MODALITY_ORDER.index(default_mod)
            except ValueError:
                default_ix = 0
            modality_ix = st.selectbox(
                "Modalidad de servicio",
                options=list(range(len(SERVICE_MODALITY_ORDER))),
                format_func=lambda i: SERVICE_MODALITY_LABELS[SERVICE_MODALITY_ORDER[i]],
                help="Para tercero, el inventario está en **Datos terceros**; la vinculación es aquí.",
                disabled=not schema_has_service_modality,
                key="cl_na_mod",
                index=default_ix,
            )
            if schema_has_service_modality:
                st.caption(SERVICE_MODALITY_HELP[SERVICE_MODALITY_ORDER[modality_ix]])
            else:
                st.caption("Ejecutá **migration_006** en Supabase para persistir la modalidad.")
            ter_new_opts = [
                r for r in tpi_rows if identity_selectable_for_new_account(r, str(r["id"]), links_by_i)
            ]
            na_tpi_options: list = [None] + [str(r["id"]) for r in ter_new_opts]

            def _fmt_cl_tpi(x):
                if x is None:
                    return "— Sin elegir —"
                return identity_option_label(tpi_by_id.get(str(x), {}))

            st.selectbox(
                "Dato de tercero (inventario)",
                options=na_tpi_options,
                format_func=_fmt_cl_tpi,
                help="Obligatorio si la modalidad es **Cuenta a nombre de tercero**.",
                key="cl_na_tpi",
            )
            if not ter_new_opts:
                st.caption("Sin fichas disponibles: cargalas en **Datos terceros**.")
            sale_type = st.selectbox(
                "Tipo",
                options=[x[0] for x in SALE_OPTIONS],
                format_func=lambda x: dict(SALE_OPTIONS)[x],
                key="cl_na_sale",
            )
            status = st.selectbox(
                "Estado inicial",
                options=[x[0] for x in STATUS_OPTIONS],
                format_func=lambda x: dict(STATUS_OPTIONS)[x],
                key="cl_na_st",
            )
            with st.container(border=True):
                st.markdown("##### Registro **solo licencia** (sin social / SSN)")
                st.caption("Si la modalidad es **Cliente con licencia — sin social**: foto(s) y precio de venta.")
                cl_na_sl_front = st.file_uploader(
                    "Foto frente de la licencia",
                    type=["jpg", "jpeg", "png", "webp"],
                    key="cl_na_slf",
                )
                cl_na_sl_back = st.file_uploader(
                    "Foto dorso (opcional)",
                    type=["jpg", "jpeg", "png", "webp"],
                    key="cl_na_slb",
                )
                cl_na_sl_price = st.number_input(
                    "Precio de venta cobrado",
                    min_value=0.0,
                    value=0.0,
                    step=10.0,
                    key="cl_na_slp",
                )
                cl_na_sl_notes = st.text_area(
                    "Notas del registro solo licencia",
                    placeholder="Opcional",
                    key="cl_na_sln",
                    height=72,
                )
            technician_id = st.selectbox(
                "Técnico (opcional)",
                options=[None] + [t["id"] for t in techs],
                format_func=lambda x: "—" if x is None else tid.get(x, str(x)),
                key="cl_na_tech",
            )
            ext = st.text_input("Referencia externa", key="cl_na_ext")
            req_notes = st.text_area("Notas de requisitos", key="cl_na_notes")
            rw = st.number_input(
                "Monto alquiler semanal (solo si aplica)", min_value=0.0, value=0.0, step=1.0, key="cl_na_rw"
            )
            sub_cl = st.form_submit_button("Crear cuenta", type="primary")
        if sub_cl:
            from datetime import datetime, timezone

            mod_key = SERVICE_MODALITY_ORDER[modality_ix] if schema_has_service_modality else None
            tpi_pick = st.session_state.get("cl_na_tpi")
            solo_err = None
            if schema_has_solo_licencia and mod_key == SOLO_LICENCIA_MODALITY:
                if not cl_na_sl_front:
                    solo_err = "Modalidad **solo licencia**: subí la **foto del frente** de la licencia."
                elif sale_type == "venta" and (not cl_na_sl_price or cl_na_sl_price <= 0):
                    solo_err = "Modalidad **solo licencia** en **Venta**: indicá el **precio cobrado** (> 0)."
            if schema_has_service_modality and mod_key == TERCERO_MODALITY and not tpi_pick:
                st.error("Elegí una ficha **disponible** del inventario para modalidad a nombre de tercero.")
            elif solo_err:
                st.error(solo_err)
            else:
                now = datetime.now(timezone.utc).isoformat()
                payload = {
                    "client_id": pre_client,
                    "platform_id": platform_id,
                    "sale_type": sale_type,
                    "status": status,
                    "technician_id": technician_id,
                    "external_ref": ext or None,
                    "requirements_notes": req_notes or None,
                }
                if schema_has_service_modality:
                    payload["service_modality"] = mod_key
                if technician_id:
                    payload["assigned_at"] = now
                if sale_type == "alquiler" and rw and rw > 0:
                    payload["rental_weekly_amount"] = float(rw)
                try:
                    ins = sb.table("accounts").insert(payload).execute()
                    new_aid = str(ins.data[0]["id"])
                    if schema_has_service_modality:
                        link_id = tpi_pick if mod_key == TERCERO_MODALITY else None
                        if mod_key == TERCERO_MODALITY and link_id:
                            verr = validate_tercero_link(sb, new_aid, str(link_id))
                            if verr:
                                sb.table("accounts").delete().eq("id", new_aid).execute()
                                st.error(verr)
                                raise RuntimeError("rollback")
                            apply_account_tercero_identity(sb, new_aid, mod_key, str(link_id))
                        else:
                            apply_account_tercero_identity(sb, new_aid, mod_key or "cuenta_nombre_tercero", None)
                    if schema_has_solo_licencia and mod_key == SOLO_LICENCIA_MODALITY:
                        ext_f = normalize_image_ext(cl_na_sl_front.name)
                        fp, _ = storage_paths_for_account(new_aid, ext_f, None)
                        storage_upload(
                            token,
                            fp,
                            cl_na_sl_front.getvalue(),
                            cl_na_sl_front.type or "image/jpeg",
                        )
                        back_path = None
                        if cl_na_sl_back:
                            ext_b = normalize_image_ext(cl_na_sl_back.name)
                            back_path = back_storage_path(new_aid, ext_b)
                            storage_upload(
                                token,
                                back_path,
                                cl_na_sl_back.getvalue(),
                                cl_na_sl_back.type or "image/jpeg",
                            )
                        upsert_solo_record(
                            sb,
                            new_aid,
                            float(cl_na_sl_price),
                            cl_na_sl_notes or None,
                            fp,
                            back_path,
                        )
                    st.cache_data.clear()
                    msg = "Cuenta creada."
                    if mod_key == TERCERO_MODALITY and tpi_pick:
                        msg = "Cuenta creada y dato de tercero vinculado."
                    elif mod_key == SOLO_LICENCIA_MODALITY:
                        msg = "Cuenta creada con registro **solo licencia** (foto y precio)."
                    st.success(msg)
                    st.rerun()
                except RuntimeError as re:
                    if str(re) != "rollback":
                        st.error(str(re))
                except Exception as e:
                    st.error(f"No se pudo crear la cuenta: {e}")

with st.expander("Nuevo cliente"):
    with st.form("new_client"):
        name = st.text_input("Nombre *")
        email = st.text_input("Email")
        phone = st.text_input("Teléfono")
        notes = st.text_area("Notas")
        default_mod_ix = st.selectbox(
            "Modalidad por defecto del cliente",
            options=list(range(len(SERVICE_MODALITY_ORDER))),
            format_func=lambda i: SERVICE_MODALITY_LABELS[SERVICE_MODALITY_ORDER[i]],
            index=0,
            help="Se sugerirá automáticamente al crear cuentas para este cliente.",
            key="cl_def_mod",
        )
        submitted = st.form_submit_button("Guardar")
    if submitted:
        if not name.strip():
            st.warning("El nombre es obligatorio.")
        else:
            sb.table("clients").insert(
                {
                    "name": name.strip(),
                    "email": email or None,
                    "phone": phone or None,
                    "notes": notes or None,
                    "default_service_modality": SERVICE_MODALITY_ORDER[default_mod_ix],
                }
            ).execute()
            st.cache_data.clear()
            st.success("Cliente creado.")
            st.rerun()

with st.expander("✏️ Editar modalidad por defecto del cliente", expanded=False):
    if not rows:
        st.info("Crea al menos un cliente primero.")
    else:
        pick = st.selectbox(
            "Cliente",
            options=[c["id"] for c in rows],
            format_func=lambda x: cid.get(x, str(x)),
            key="cl_edit_pick",
        )
        cur_mod = client_default_mod.get(str(pick)) or "cuenta_nombre_tercero"
        try:
            cur_ix = SERVICE_MODALITY_ORDER.index(cur_mod)
        except ValueError:
            cur_ix = 0
        with st.form("cl_edit_default_mod"):
            new_ix = st.selectbox(
                "Modalidad por defecto",
                options=list(range(len(SERVICE_MODALITY_ORDER))),
                format_func=lambda i: SERVICE_MODALITY_LABELS[SERVICE_MODALITY_ORDER[i]],
                index=cur_ix,
            )
            save = st.form_submit_button("Guardar")
        if save:
            try:
                sb.table("clients").update({"default_service_modality": SERVICE_MODALITY_ORDER[new_ix]}).eq("id", pick).execute()
                st.cache_data.clear()
                st.success("Actualizado.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo actualizar: {e}")
