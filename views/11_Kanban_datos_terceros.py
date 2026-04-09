import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.constants import (
    TPI_DATA_SEMAPHORE_COLOR,
    TPI_DATA_SEMAPHORE_LABELS,
    TPI_KANBAN_COLUMNS,
    TPI_WORKFLOW_LABELS,
    TPI_WORKFLOW_ORDER,
)
from src.db import get_client
from src.rbac import (
    DATOS_TERCEROS_KANBAN_ROLES,
    ROLE_ADMIN,
    ROLE_SUPER,
    ROLE_TECNICO,
    ROLE_VENDEDOR,
    get_my_technician_row,
    require_login,
    require_roles,
)

st.title("Tablero de solicitudes — Datos terceros")
st.caption(
    "Cada tarjeta es una solicitud de dato de tercero: **cliente** que pide, **técnico** que ejecuta. "
    "Actualizá el **estado del flujo** o marcá **Background malo** si el dato no debe usarse más."
)

if not supabase_configured():
    st.error("Configura Supabase.")
    st.stop()

require_login()
require_roles(DATOS_TERCEROS_KANBAN_ROLES)

token = st.session_state.access_token
sb = get_client(token)
role = st.session_state.user_role


def _is_malo(row: dict) -> bool:
    return row.get("data_semaphore") == "background_malo"


def _can_operate_row(row: dict, my_tech: dict | None) -> bool:
    if role in (ROLE_SUPER, ROLE_ADMIN, ROLE_VENDEDOR):
        return True
    if role == ROLE_TECNICO and my_tech:
        return str(row.get("assigned_technician_id") or "") == str(my_tech["id"])
    return False


@st.cache_data(ttl=20)
def load_identities_all(_token: str):
    c = get_client(_token)
    r = c.table("third_party_identities").select("*").order("created_at", desc=True).execute()
    return r.data or []


@st.cache_data(ttl=60)
def load_client_names(_token: str):
    c = get_client(_token)
    rows = (c.table("clients").select("id,name").execute().data) or []
    return {str(x["id"]): x.get("name") or "—" for x in rows}


@st.cache_data(ttl=60)
def load_tech_names(_token: str):
    c = get_client(_token)
    rows = (c.table("technicians").select("id,name").execute().data) or []
    return {str(x["id"]): x.get("name") or "—" for x in rows}


if st.button("Refrescar tablero"):
    st.cache_data.clear()
    st.rerun()

try:
    all_rows = load_identities_all(token)
    cnames = load_client_names(token)
    tnames = load_tech_names(token)
except Exception as e:
    st.error(f"Error al cargar: {e}")
    st.info("¿Ejecutaste **migration_007_third_party_workflow.sql**?")
    st.stop()

my_tech = get_my_technician_row(token) if role == ROLE_TECNICO else None
if role == ROLE_TECNICO and not my_tech:
    st.warning(
        "Tu usuario **no está vinculado** a un registro de **técnico** (`technicians.auth_user_id`). "
        "Un administrador debe asignarlo para que veas tarjetas aquí."
    )

if role == ROLE_TECNICO and my_tech:
    rows = [r for r in all_rows if str(r.get("assigned_technician_id") or "") == str(my_tech["id"])]
else:
    rows = all_rows


def _bucket(data: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {k: [] for k, _ in TPI_KANBAN_COLUMNS}
    for r in data:
        if _is_malo(r):
            out["dato_malo"].append(r)
            continue
        w = r.get("workflow_status") or "solicitud"
        if w not in out:
            w = "solicitud"
        out[w].append(r)
    return out


buckets = _bucket(rows)

tab_labels = [lbl for _, lbl in TPI_KANBAN_COLUMNS]
tabs = st.tabs(tab_labels)

for ti, (col_key, col_title) in enumerate(TPI_KANBAN_COLUMNS):
    with tabs[ti]:
        items = buckets.get(col_key, [])
        if not items:
            with st.container(border=True):
                st.caption("Sin tarjetas en esta columna.")
            continue
        for r in items:
            rid = str(r["id"])
            sem = r.get("data_semaphore") or "revisar"
            sem_lbl = TPI_DATA_SEMAPHORE_LABELS.get(sem, sem)
            sem_col = TPI_DATA_SEMAPHORE_COLOR.get(sem, "#757575")
            cli = cnames.get(str(r.get("request_client_id") or ""), "—")
            tec = tnames.get(str(r.get("assigned_technician_id") or ""), "Sin técnico")
            wf = r.get("workflow_status") or "—"

            with st.container(border=True):
                st.markdown(
                    f"**{r.get('first_name', '')} {r.get('last_name', '')}** · Lic. `{r.get('license_number', '')}`"
                )
                st.markdown(
                    f"<span style='color:{sem_col};font-weight:600;'>● Semáforo: {sem_lbl}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Cliente solicitud: **{cli}** · Técnico: **{tec}** · Flujo: **{TPI_WORKFLOW_LABELS.get(wf, wf)}**")

                op = _can_operate_row(r, my_tech)

                if col_key == "dato_malo":
                    st.error("Dato **inutilizable**: no se asigna a cuentas nuevas. Revisá o recreá el registro desde **Datos terceros**.")
                    continue

                if not op:
                    st.caption("Solo el técnico asignado o personal comercial/admin puede mover esta tarjeta.")
                    continue

                move_opts = [w for w in TPI_WORKFLOW_ORDER if w != r.get("workflow_status")]
                if move_opts:
                    pick = st.selectbox(
                        "Mover a etapa",
                        options=move_opts,
                        format_func=lambda w: TPI_WORKFLOW_LABELS.get(w, w),
                        key=f"kb_mv_{rid}_{ti}",
                    )
                    if st.button("Aplicar movimiento", key=f"kb_go_{rid}_{ti}"):
                        try:
                            sb.table("third_party_identities").update({"workflow_status": pick}).eq("id", rid).execute()
                            st.cache_data.clear()
                            st.success("Estado actualizado.")
                            st.rerun()
                        except Exception as ex:
                            st.error(str(ex))

                if role in (ROLE_SUPER, ROLE_ADMIN, ROLE_VENDEDOR) or (
                    role == ROLE_TECNICO and my_tech and str(r.get("assigned_technician_id")) == str(my_tech["id"])
                ):
                    if st.button("Marcar Background malo (bloquear dato)", key=f"kb_bad_{rid}_{ti}", type="primary"):
                        try:
                            sb.table("account_identity_links").delete().eq("identity_id", rid).execute()
                            sb.table("third_party_identities").update(
                                {"data_semaphore": "background_malo", "workflow_status": "cerrado"}
                            ).eq("id", rid).execute()
                            st.cache_data.clear()
                            st.success("Dato marcado como Background malo; vínculos a cuentas eliminados.")
                            st.rerun()
                        except Exception as ex:
                            st.error(str(ex))
