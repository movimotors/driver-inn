"""Control de sesión y roles en Streamlit."""

from __future__ import annotations

import streamlit as st

from src.config import supabase_configured
from src.db import get_client

ROLE_SUPER = "superusuario"
ROLE_ADMIN = "administracion"
ROLE_VENDEDOR = "vendedor"
ROLE_TECNICO = "tecnico"

ROLE_LABELS = {
    ROLE_SUPER: "Super usuario",
    ROLE_ADMIN: "Administración",
    ROLE_VENDEDOR: "Vendedor",
    ROLE_TECNICO: "Técnico",
}

ALL_ROLES = [ROLE_SUPER, ROLE_ADMIN, ROLE_VENDEDOR, ROLE_TECNICO]

# Finanzas (por pagar / cobrar / gastos): sin técnico
FINANCE_ROLES = [ROLE_SUPER, ROLE_ADMIN, ROLE_VENDEDOR]


def init_session_state():
    defaults = {
        "access_token": None,
        "refresh_token": None,
        "user_id": None,
        "user_email": None,
        "user_role": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def is_logged_in() -> bool:
    init_session_state()
    return bool(st.session_state.access_token and st.session_state.user_id)


def logout():
    init_session_state()
    for k in ("access_token", "user_id", "user_email", "user_role", "refresh_token"):
        st.session_state[k] = None
    st.cache_data.clear()


def fetch_profile_for_user(access_token: str, user_id: str) -> dict | None:
    client = get_client(access_token)
    r = client.table("profiles").select("id,email,full_name,role").eq("id", user_id).execute()
    rows = r.data or []
    return rows[0] if rows else None


def require_login():
    init_session_state()
    if not supabase_configured():
        st.error("Configura Supabase (variables de entorno o secrets).")
        st.stop()
    if not is_logged_in():
        st.warning("Iniciá sesión desde la página principal (**Home**).")
        if st.button("Ir a inicio de sesión"):
            st.switch_page("Home.py")
        st.stop()


def require_roles(allowed: list[str]):
    require_login()
    role = st.session_state.user_role
    if role not in allowed:
        st.error("No tenés permiso para ver esta sección.")
        st.stop()


def has_role(*roles: str) -> bool:
    init_session_state()
    return st.session_state.user_role in roles


def can_delete_finance_records() -> bool:
    return has_role(ROLE_SUPER, ROLE_ADMIN)


def can_edit_telecom_inventory() -> bool:
    """Alta/edición/baja de inventario telecom (RLS: solo super + administración)."""
    return has_role(ROLE_SUPER, ROLE_ADMIN)


def current_role_label() -> str:
    r = st.session_state.get("user_role")
    return ROLE_LABELS.get(r, r or "—")
