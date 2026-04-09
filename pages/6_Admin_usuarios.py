import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.db import get_client
from src.rbac import ALL_ROLES, ROLE_LABELS, ROLE_ADMIN, ROLE_SUPER, require_roles

st.set_page_config(page_title="Admin usuarios", layout="wide")
st.title("Administración de usuarios y roles")

require_roles([ROLE_SUPER, ROLE_ADMIN])

token = st.session_state.access_token
sb = get_client(token)

if st.session_state.user_role == ROLE_ADMIN:
    st.info("Como **administración** no podés asignar ni modificar cuentas **super usuario**.")

if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()


@st.cache_data(ttl=20)
def load_profiles(_token: str):
    c = get_client(_token)
    r = c.table("profiles").select("id,email,full_name,role,created_at").order("created_at", desc=True).execute()
    return r.data or []


rows = load_profiles(token)
st.dataframe(rows, use_container_width=True, hide_index=True)

st.subheader("Cambiar rol de un usuario")
if not rows:
    st.stop()

by_id = {r["id"]: r for r in rows}
options = list(by_id.keys())


def _label(uid: str) -> str:
    r = by_id[uid]
    return f"{r.get('email') or uid[:8]} — {ROLE_LABELS.get(r.get('role'), r.get('role'))}"


pick = st.selectbox("Usuario", options=options, format_func=_label)
current = by_id[pick]
cur_role = current.get("role")

if st.session_state.user_role == ROLE_ADMIN and cur_role == ROLE_SUPER:
    st.warning("No podés editar un super usuario.")
    st.stop()

allowed_new = list(ALL_ROLES) if st.session_state.user_role == ROLE_SUPER else [r for r in ALL_ROLES if r != ROLE_SUPER]
try:
    idx = allowed_new.index(cur_role) if cur_role in allowed_new else 0
except ValueError:
    idx = 0

new_role = st.selectbox(
    "Nuevo rol",
    options=allowed_new,
    format_func=lambda x: ROLE_LABELS[x],
    index=idx,
)

if st.session_state.user_role == ROLE_ADMIN and new_role == ROLE_SUPER:
    st.error("No podés promover a super usuario.")
    st.stop()

if st.button("Guardar rol", type="primary"):
    if new_role == cur_role:
        st.info("Sin cambios.")
    else:
        sb.table("profiles").update({"role": new_role}).eq("id", pick).execute()
        st.cache_data.clear()
        st.success("Rol actualizado.")
        st.rerun()

st.subheader("Vincular técnico con usuario (Auth)")
st.caption(
    "En Supabase, en la tabla **technicians**, completá **auth_user_id** con el UUID del usuario "
    "(Authentication → Users). Así el rol **técnico** solo ve cuentas asignadas a ese técnico."
)
