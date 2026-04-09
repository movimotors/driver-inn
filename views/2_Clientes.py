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
from src.account_solo_licencia import solo_table_available
from src.db import fetch_accounts_list_with_modality_fallback, get_client
from src.rbac import ROLE_ADMIN, ROLE_SUPER, ROLE_VENDEDOR, require_roles
from src.tpi_account_linking import load_identities_and_links
from src.account_create_flow import render_account_create_form

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
        res = render_account_create_form(
            sb=sb,
            token=token,
            key_prefix="clientes",
            schema_has_service_modality=schema_has_service_modality,
            schema_has_solo_licencia=schema_has_solo_licencia,
            service_modality_order=SERVICE_MODALITY_ORDER,
            service_modality_labels=SERVICE_MODALITY_LABELS,
            service_modality_help=SERVICE_MODALITY_HELP,
            clients=rows,
            client_id_default_modality=client_default_mod,
            plats=plats,
            techs=techs,
            tpi_rows=tpi_rows,
            links_by_i=links_by_i,
            status_options=STATUS_OPTIONS,
            sale_options=SALE_OPTIONS,
            preset_client_id=str(pre_client),
        )
        if res.created:
            st.cache_data.clear()
            st.success(res.message or "Cuenta creada.")
            st.rerun()

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
