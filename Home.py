import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.rbac import ROLE_LABELS, get_nav_sections_for_role, init_session_state, is_logged_in, logout
from views.login_screen import render_auth_screen

st.set_page_config(
    page_title="Driver Inn",
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
    _sections = get_nav_sections_for_role(st.session_state.user_role)
    _nav_groups: dict[str, list] = {}
    for _name, _pages in _sections.items():
        _nav_groups[_name] = [
            st.Page(pg.path, title=pg.title, icon=pg.icon, default=pg.default) for pg in _pages
        ]
    nav = st.navigation(_nav_groups)
except TypeError as e:
    st.error(
        "Tu versión de Streamlit es antigua. Ejecutá: `pip install -U 'streamlit>=1.36'` "
        f"({e})"
    )
    st.stop()

nav.run()
