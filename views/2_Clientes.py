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
from src.db import fetch_accounts_list_with_modality_fallback, get_client
from src.rbac import ROLE_ADMIN, ROLE_SUPER, ROLE_VENDEDOR, require_roles
from src.tpi_account_linking import load_identities_and_links

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
    _, schema_has_service_modality = load_accounts_schema(token)
except Exception:
    schema_has_service_modality = False


with st.expander("➕ Nuevo cliente", expanded=False):
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
            ins = sb.table("clients").insert(
                {
                    "name": name.strip(),
                    "email": email or None,
                    "phone": phone or None,
                    "notes": notes or None,
                    "default_service_modality": SERVICE_MODALITY_ORDER[default_mod_ix],
                }
            ).execute()
            st.cache_data.clear()
            new_id = str(ins.data[0]["id"]) if ins.data else None
            if new_id:
                st.session_state["prefill_account_create_client_id"] = new_id
            st.success("Cliente creado. Continuá en **Cuentas** para crear la cuenta según la modalidad.")
            st.switch_page("views/4_Cuentas.py")

with st.expander("✏️ Editar cliente", expanded=False):
    if not rows:
        st.info("Crea al menos un cliente primero.")
    else:
        pick = st.selectbox(
            "Cliente",
            options=[c["id"] for c in rows],
            format_func=lambda x: cid.get(x, str(x)),
            key="cl_edit_pick",
        )
        cur = next((r for r in rows if str(r.get("id")) == str(pick)), {}) or {}
        cur_mod = client_default_mod.get(str(pick)) or cur.get("default_service_modality") or "cuenta_nombre_tercero"
        try:
            cur_ix = SERVICE_MODALITY_ORDER.index(cur_mod)
        except ValueError:
            cur_ix = 0
        with st.form("cl_edit_client"):
            name = st.text_input("Nombre *", value=cur.get("name") or "")
            email = st.text_input("Email", value=cur.get("email") or "")
            phone = st.text_input("Teléfono", value=cur.get("phone") or "")
            notes = st.text_area("Notas", value=cur.get("notes") or "")
            new_ix = st.selectbox(
                "Modalidad por defecto",
                options=list(range(len(SERVICE_MODALITY_ORDER))),
                format_func=lambda i: SERVICE_MODALITY_LABELS[SERVICE_MODALITY_ORDER[i]],
                index=cur_ix,
            )
            save = st.form_submit_button("Guardar")
        if save:
            try:
                if not name.strip():
                    st.error("El nombre es obligatorio.")
                else:
                    sb.table("clients").update(
                        {
                            "name": name.strip(),
                            "email": email or None,
                            "phone": phone or None,
                            "notes": notes or None,
                            "default_service_modality": SERVICE_MODALITY_ORDER[new_ix],
                        }
                    ).eq("id", pick).execute()
                st.cache_data.clear()
                st.success("Actualizado.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo actualizar: {e}")
