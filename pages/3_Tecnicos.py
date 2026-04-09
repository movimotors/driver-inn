import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.db import get_client
from src.rbac import ROLE_ADMIN, ROLE_SUPER, require_roles

st.set_page_config(page_title="Técnicos", layout="wide")
st.title("Técnicos")

if not supabase_configured():
    st.error("Configura `.env` con Supabase.")
    st.stop()

require_roles([ROLE_SUPER, ROLE_ADMIN])

token = st.session_state.access_token
sb = get_client(token)


@st.cache_data(ttl=30)
def list_technicians(_token: str):
    c = get_client(_token)
    r = c.table("technicians").select("*").order("created_at", desc=True).execute()
    return r.data or []


if st.button("Refrescar lista"):
    st.cache_data.clear()
    st.rerun()

rows = list_technicians(token)
st.dataframe(rows, use_container_width=True, hide_index=True)

with st.expander("Nuevo técnico"):
    with st.form("new_tech"):
        name = st.text_input("Nombre *")
        email = st.text_input("Email")
        phone = st.text_input("Teléfono")
        active = st.checkbox("Activo", value=True)
        submitted = st.form_submit_button("Guardar")
    if submitted:
        if not name.strip():
            st.warning("El nombre es obligatorio.")
        else:
            sb.table("technicians").insert(
                {
                    "name": name.strip(),
                    "email": email or None,
                    "phone": phone or None,
                    "active": active,
                }
            ).execute()
            st.cache_data.clear()
            st.success("Técnico creado.")
            st.rerun()
