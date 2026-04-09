import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.rbac import ROLE_LABELS, init_session_state, is_logged_in, logout
from views.login_screen import render_auth_screen

st.set_page_config(
    page_title="Delivery Control",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()

# --- Solo pantalla de acceso: sin menú de la aplicación ---
if not is_logged_in():
    render_auth_screen()
    st.stop()

# --- Sesión iniciada: navegación interna (carpeta views/, ya no pages/) ---
with st.sidebar:
    st.markdown(f"**{st.session_state.user_email or 'Usuario'}**")
    st.caption(ROLE_LABELS.get(st.session_state.user_role, st.session_state.user_role or ""))
    if st.button("Cerrar sesión", use_container_width=True):
        logout()
        st.rerun()

try:
    nav = st.navigation(
        {
            "Operación": [
                st.Page("views/1_Dashboard.py", title="Dashboard", icon="📊", default=True),
                st.Page("views/2_Clientes.py", title="Clientes", icon="👤"),
                st.Page("views/3_Tecnicos.py", title="Técnicos", icon="🔧"),
                st.Page("views/4_Cuentas.py", title="Cuentas", icon="📦"),
                st.Page("views/5_Alquileres_y_alertas.py", title="Alquileres", icon="💳"),
            ],
            "Finanzas e inventario": [
                st.Page("views/7_Por_pagar.py", title="Por pagar", icon="📤"),
                st.Page("views/8_Por_cobrar.py", title="Por cobrar", icon="📥"),
                st.Page("views/9_Gastos_operativos.py", title="Gastos", icon="🧾"),
                st.Page("views/10_Inventario_telecom.py", title="Inventario telecom", icon="📡"),
            ],
            "Administración": [
                st.Page("views/6_Admin_usuarios.py", title="Usuarios y roles", icon="⚙️"),
            ],
        }
    )
except TypeError as e:
    st.error(
        "Tu versión de Streamlit es antigua. Ejecutá: `pip install -U 'streamlit>=1.36'` "
        f"({e})"
    )
    st.stop()

nav.run()
