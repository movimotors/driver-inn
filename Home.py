import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import get_supabase_config, supabase_configured

st.set_page_config(
    page_title="Delivery Control",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Delivery Control — Asesoría y gestión de cuentas (USA)")
st.markdown(
    """
Esta aplicación centraliza **clientes**, **técnicos** y **cuentas** de plataformas tipo
Instacart, Uber Eats, Lyft, Spark, Amazon Flex, Veho y DoorDash, con un **semáforo de estado**
y seguimiento de **ventas vs alquiler**.

Usa el menú lateral para **Dashboard**, **Clientes**, **Técnicos**, **Cuentas** y **Alquileres y alertas**.
"""
)

st.subheader("Conexión a Supabase")
if supabase_configured():
    url, _ = get_supabase_config()
    st.success(f"Variables de entorno cargadas. URL: `{url[:40]}…`")
else:
    st.warning(
        "No hay `SUPABASE_URL` / `SUPABASE_KEY`. Copia `.env.example` a `.env` "
        "o define las variables antes de ejecutar Streamlit."
    )
    st.code("copy .env.example .env\n# edita .env con tus credenciales", language="bash")

st.divider()
st.caption("Streamlit multipágina · Supabase · preparado para GitHub")
