"""Control de sesión y roles en Streamlit."""

from __future__ import annotations

from dataclasses import dataclass

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

# Registro público: solo estos (super/admin los asigna un administrador).
SELF_SIGNUP_ROLE_OPTIONS: dict[str, str] = {
    ROLE_VENDEDOR: "Vendedor — clientes, cuentas, alquileres y finanzas",
    ROLE_TECNICO: "Técnico — cuentas asignadas y datos terceros vinculados a esas cuentas",
}

# Finanzas (por pagar / cobrar / gastos): sin técnico
FINANCE_ROLES = [ROLE_SUPER, ROLE_ADMIN, ROLE_VENDEDOR]


@dataclass(frozen=True)
class NavPage:
    path: str
    title: str
    icon: str
    default: bool = False


def _nav_full() -> dict[str, list[NavPage]]:
    return {
        "Operación": [
            NavPage("views/1_Dashboard.py", "Dashboard", "📊", default=True),
            NavPage("views/2_Clientes.py", "Clientes", "👤"),
            NavPage("views/3_Tecnicos.py", "Técnicos", "🔧"),
            NavPage("views/4_Cuentas.py", "Cuentas", "📦"),
            NavPage("views/5_Alquileres_y_alertas.py", "Alquileres", "💳"),
        ],
        "Finanzas e inventario": [
            NavPage("views/7_Por_pagar.py", "Por pagar", "📤"),
            NavPage("views/8_Por_cobrar.py", "Por cobrar", "📥"),
            NavPage("views/9_Gastos_operativos.py", "Gastos", "🧾"),
            NavPage("views/10_Datos_terceros.py", "Datos terceros", "🪪"),
        ],
        "Administración": [
            NavPage("views/6_Admin_usuarios.py", "Usuarios y roles", "⚙️"),
        ],
    }


def _nav_vendedor() -> dict[str, list[NavPage]]:
    return {
        "Operación": [
            NavPage("views/1_Dashboard.py", "Dashboard", "📊", default=True),
            NavPage("views/2_Clientes.py", "Clientes", "👤"),
            NavPage("views/4_Cuentas.py", "Cuentas", "📦"),
            NavPage("views/5_Alquileres_y_alertas.py", "Alquileres", "💳"),
        ],
        "Finanzas e inventario": [
            NavPage("views/7_Por_pagar.py", "Por pagar", "📤"),
            NavPage("views/8_Por_cobrar.py", "Por cobrar", "📥"),
            NavPage("views/9_Gastos_operativos.py", "Gastos", "🧾"),
            NavPage("views/10_Datos_terceros.py", "Datos terceros", "🪪"),
        ],
    }


def _nav_tecnico() -> dict[str, list[NavPage]]:
    return {
        "Operación": [
            NavPage("views/1_Dashboard.py", "Dashboard", "📊", default=True),
            NavPage("views/4_Cuentas.py", "Cuentas", "📦"),
        ],
        "Recursos": [
            NavPage("views/10_Datos_terceros.py", "Datos terceros", "🪪"),
        ],
    }


def get_nav_sections_for_role(role: str | None) -> dict[str, list[NavPage]]:
    """Menú lateral según rol (coherente con require_roles en cada vista)."""
    r = role or ROLE_TECNICO
    if r in (ROLE_SUPER, ROLE_ADMIN):
        return _nav_full()
    if r == ROLE_VENDEDOR:
        return _nav_vendedor()
    return _nav_tecnico()


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
        # Lleva a Home: ahí está el formulario de login (el menú lateral puede abrir otra página primero).
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


def can_edit_datos_terceros() -> bool:
    """Alta/edición de licencias / datos terceros (RLS: super, administración, vendedor)."""
    return has_role(ROLE_SUPER, ROLE_ADMIN, ROLE_VENDEDOR)


def can_delete_datos_terceros() -> bool:
    """Baja de registros de datos terceros (RLS: super y administración)."""
    return has_role(ROLE_SUPER, ROLE_ADMIN)


def can_edit_telecom_inventory() -> bool:
    """Compatibilidad: antes inventario telecom; ahora mismo criterio que datos terceros."""
    return can_edit_datos_terceros()


def current_role_label() -> str:
    r = st.session_state.get("user_role")
    return ROLE_LABELS.get(r, r or "—")
