import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.db import get_client

st.set_page_config(page_title="Clientes", layout="wide")
st.title("Clientes")

if not supabase_configured():
    st.error("Configura `.env` con Supabase.")
    st.stop()

sb = get_client()

@st.cache_data(ttl=30)
def list_clients():
    r = sb.table("clients").select("*").order("created_at", desc=True).execute()
    return r.data or []

if st.button("Refrescar lista"):
    st.cache_data.clear()
    st.rerun()

rows = list_clients()
st.dataframe(rows, use_container_width=True, hide_index=True)

with st.expander("Nuevo cliente"):
    with st.form("new_client"):
        name = st.text_input("Nombre *")
        email = st.text_input("Email")
        phone = st.text_input("Teléfono")
        notes = st.text_area("Notas")
        submitted = st.form_submit_button("Guardar")
    if submitted:
        if not name.strip():
            st.warning("El nombre es obligatorio.")
        else:
            sb.table("clients").insert(
                {"name": name.strip(), "email": email or None, "phone": phone or None, "notes": notes or None}
            ).execute()
            st.cache_data.clear()
            st.success("Cliente creado.")
            st.rerun()
