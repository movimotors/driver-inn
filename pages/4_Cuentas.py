import sys
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.constants import ACCOUNT_STATUS_COLOR, ACCOUNT_STATUS_LABELS, ACCOUNT_STATUS_ORDER, SALE_TYPE_LABELS
from src.db import get_client
from src.rbac import ROLE_TECNICO, require_login

st.set_page_config(page_title="Cuentas", layout="wide")
st.title("Cuentas delivery — semáforo de estado")

if not supabase_configured():
    st.error("Configura `.env` con Supabase.")
    st.stop()

require_login()
token = st.session_state.access_token
sb = get_client(token)

STATUS_OPTIONS = [(s, ACCOUNT_STATUS_LABELS[s]) for s in ACCOUNT_STATUS_ORDER]
SALE_OPTIONS = [("venta", "Venta"), ("alquiler", "Alquiler")]
can_create = st.session_state.user_role != ROLE_TECNICO


@st.cache_data(ttl=30)
def load_lookups(_token: str):
    c = get_client(_token)
    clients = (c.table("clients").select("id,name").order("name").execute().data) or []
    techs = (c.table("technicians").select("id,name,active").eq("active", True).order("name").execute().data) or []
    plats = (c.table("delivery_platforms").select("id,name,code").eq("active", True).order("name").execute().data) or []
    return clients, techs, plats


@st.cache_data(ttl=30)
def load_accounts_full(_token: str):
    c = get_client(_token)
    r = (
        c.table("accounts")
        .select(
            "id, client_id, platform_id, technician_id, sale_type, status, requirements_notes, "
            "assigned_at, delivered_at, rental_weekly_amount, rental_next_due_date, external_ref, created_at"
        )
        .order("created_at", desc=True)
        .execute()
    )
    return r.data or []


def status_badge(status: str) -> str:
    label = ACCOUNT_STATUS_LABELS.get(status, status)
    color = ACCOUNT_STATUS_COLOR.get(status, "#757575")
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{label}</span>'


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

try:
    clients, techs, plats = load_lookups(token)
    accounts = load_accounts_full(token)
except Exception as e:
    st.error(f"Error al cargar datos: {e}")
    st.stop()

cid = {c["id"]: c["name"] for c in clients}
tid = {t["id"]: t["name"] for t in techs}
pid = {p["id"]: p["name"] for p in plats}

st.subheader("Leyenda del semáforo")
cols = st.columns(len(ACCOUNT_STATUS_ORDER[:5]))
for i, s in enumerate(ACCOUNT_STATUS_ORDER[:5]):
    cols[i].markdown(status_badge(s), unsafe_allow_html=True)
st.caption("Suspendida / Cancelada: rojo y gris en la tabla de estados.")

st.subheader("Listado")
for row in accounts:
    plat = pid.get(row["platform_id"], row["platform_id"])
    cli = cid.get(row["client_id"], row["client_id"])
    tech = tid.get(row["technician_id"], "—") if row.get("technician_id") else "Sin asignar"
    badge = status_badge(row["status"])
    st.markdown(
        f"**{plat}** · Cliente: {cli} · Técnico: {tech} · "
        f"{SALE_TYPE_LABELS.get(row['sale_type'], row['sale_type'])} — {badge}",
        unsafe_allow_html=True,
    )
    if row.get("requirements_notes"):
        st.caption(row["requirements_notes"][:200] + ("…" if len(row["requirements_notes"] or "") > 200 else ""))
    st.divider()

if can_create:
    st.subheader("Nueva cuenta")
    if not clients or not plats:
        st.warning("Necesitás al menos un cliente y plataformas cargadas.")
    else:
        with st.form("new_account"):
            client_id = st.selectbox("Cliente", options=[c["id"] for c in clients], format_func=lambda x: cid[x], key="na_c")
            platform_id = st.selectbox(
                "Plataforma", options=[p["id"] for p in plats], format_func=lambda x: pid[x], key="na_p"
            )
            sale_type = st.selectbox("Tipo", options=[x[0] for x in SALE_OPTIONS], format_func=lambda x: dict(SALE_OPTIONS)[x])
            status = st.selectbox(
                "Estado inicial", options=[x[0] for x in STATUS_OPTIONS], format_func=lambda x: dict(STATUS_OPTIONS)[x]
            )
            technician_id = st.selectbox(
                "Técnico (opcional)",
                options=[None] + [t["id"] for t in techs],
                format_func=lambda x: "—" if x is None else tid[x],
            )
            ext = st.text_input("Referencia externa")
            req_notes = st.text_area("Notas de requisitos")
            rw = st.number_input("Monto alquiler semanal (solo si aplica)", min_value=0.0, value=0.0, step=1.0)
            submitted = st.form_submit_button("Crear cuenta")
        if submitted:
            from datetime import timezone

            now = datetime.now(timezone.utc).isoformat()
            payload = {
                "client_id": client_id,
                "platform_id": platform_id,
                "sale_type": sale_type,
                "status": status,
                "technician_id": technician_id,
                "external_ref": ext or None,
                "requirements_notes": req_notes or None,
            }
            if technician_id:
                payload["assigned_at"] = now
            if sale_type == "alquiler" and rw and rw > 0:
                payload["rental_weekly_amount"] = float(rw)
            try:
                sb.table("accounts").insert(payload).execute()
                st.cache_data.clear()
                st.success("Cuenta creada.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo crear: {e}")
else:
    st.caption("Los técnicos no crean cuentas nuevas desde la app; solo actualizan las asignadas.")

st.subheader("Actualizar cuenta existente")
if not accounts:
    st.info("Crea al menos una cuenta arriba (si tenés permiso).")
else:

    def _acc_label(aid: str) -> str:
        cur = next(a for a in accounts if a["id"] == aid)
        p = pid.get(cur["platform_id"], "?")
        c = cid.get(cur["client_id"], "?")
        return f"{p} · {c} ({aid[:8]}…)"

    acc = st.selectbox("Seleccionar cuenta", options=[a["id"] for a in accounts], format_func=_acc_label)
    current = next(a for a in accounts if a["id"] == acc)
    tech_options: list = [None] + [t["id"] for t in techs]
    try:
        tech_index = tech_options.index(current.get("technician_id"))
    except ValueError:
        tech_index = 0
    try:
        st_index = ACCOUNT_STATUS_ORDER.index(current["status"])
    except ValueError:
        st_index = 0

    with st.form("upd_account"):
        new_status = st.selectbox(
            "Estado",
            options=[x[0] for x in STATUS_OPTIONS],
            format_func=lambda x: dict(STATUS_OPTIONS)[x],
            index=st_index,
        )
        new_tech = st.selectbox(
            "Técnico",
            options=tech_options,
            format_func=lambda x: "—" if x is None else tid.get(x, str(x)),
            index=tech_index,
        )
        set_delivered = st.checkbox("Registrar / actualizar fecha de entrega")
        delivered = st.date_input("Fecha entregada", value=None) if set_delivered else None
        set_rental_due = st.checkbox("Fijar próximo vencimiento de alquiler")
        rental_due = st.date_input("Próximo vencimiento alquiler", value=None) if set_rental_due else None
        note_event = st.text_input("Nota del cambio (auditoría)")
        save = st.form_submit_button("Guardar cambios")
    if save:
        old_st = current["status"]
        upd = {"status": new_status, "technician_id": new_tech}
        from datetime import timezone

        if new_tech and not current.get("technician_id"):
            upd["assigned_at"] = datetime.now(timezone.utc).isoformat()
        if set_delivered and delivered:
            upd["delivered_at"] = delivered.isoformat()
        if set_rental_due and rental_due:
            upd["rental_next_due_date"] = rental_due.isoformat()
        try:
            sb.table("accounts").update(upd).eq("id", acc).execute()
            if old_st != new_status:
                sb.table("account_status_events").insert(
                    {
                        "account_id": acc,
                        "old_status": old_st,
                        "new_status": new_status,
                        "note": note_event or None,
                    }
                ).execute()
            st.cache_data.clear()
            st.success("Cuenta actualizada.")
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")
