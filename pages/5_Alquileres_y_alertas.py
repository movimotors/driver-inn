import sys
from pathlib import Path
from datetime import date, timedelta

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

from src.config import supabase_configured
from src.db import get_client

st.set_page_config(page_title="Alquileres", layout="wide")
st.title("Alquileres, pagos y alertas")

if not supabase_configured():
    st.error("Configura `.env` con Supabase.")
    st.stop()

sb = get_client()


@st.cache_data(ttl=30)
def rental_accounts():
    r = (
        sb.table("accounts")
        .select("id, client_id, platform_id, rental_weekly_amount, rental_next_due_date, delivered_at, status")
        .eq("sale_type", "alquiler")
        .execute()
    )
    return r.data or []


@st.cache_data(ttl=30)
def payments_for(account_id: str):
    r = (
        sb.table("rental_payments")
        .select("*")
        .eq("account_id", account_id)
        .order("due_date", desc=True)
        .execute()
    )
    return r.data or []


@st.cache_data(ttl=60)
def lookups():
    clients = {c["id"]: c["name"] for c in ((sb.table("clients").select("id,name").execute().data) or [])}
    plats = {p["id"]: p["name"] for p in ((sb.table("delivery_platforms").select("id,name").execute().data) or [])}
    return clients, plats


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

accounts = rental_accounts()
clients, plats = lookups()
today = date.today()

st.subheader("Cuentas en alquiler — vencimientos")
rows = []
for a in accounts:
    due = a.get("rental_next_due_date")
    d = None
    if due:
        d = date.fromisoformat(str(due)[:10]) if isinstance(due, str) else due
    if d is None:
        flag = "sin fecha"
    elif d < today:
        flag = "vencido"
    elif d <= today + timedelta(days=7):
        flag = "próxima semana"
    else:
        flag = "al día"
    rows.append(
        {
            "cuenta_id": a["id"][:8] + "…",
            "cliente": clients.get(a["client_id"], a["client_id"]),
            "plataforma": plats.get(a["platform_id"], a["platform_id"]),
            "semanal": a.get("rental_weekly_amount"),
            "vence": d.isoformat() if d else None,
            "alerta": flag,
            "estado_cuenta": a.get("status"),
            "entregada": a.get("delivered_at"),
        }
    )

if not rows:
    st.info("No hay cuentas marcadas como alquiler. En **Cuentas**, crea o edita con tipo **Alquiler**.")
else:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.subheader("Registrar pago semanal")
if not accounts:
    st.stop()

acc_ids = [a["id"] for a in accounts]


def _pay_label(aid: str) -> str:
    a = next(x for x in accounts if x["id"] == aid)
    return f"{plats.get(a['platform_id'])} · {clients.get(a['client_id'])} ({aid[:8]}…)"


sel = st.selectbox("Cuenta (alquiler)", options=acc_ids, format_func=_pay_label)

with st.form("pay"):
    amount = st.number_input("Monto", min_value=0.01, value=float(next(a for a in accounts if a["id"] == sel).get("rental_weekly_amount") or 0) or 1.0)
    due = st.date_input("Período / vencimiento", value=today)
    period_label = st.text_input("Etiqueta (ej. semana 2026-W14)")
    notes = st.text_area("Notas")
    mark_paid = st.checkbox("Marcar como pagado ahora", value=True)
    advance_next = st.checkbox("Adelantar próximo vencimiento +7 días en la cuenta", value=True)
    sub = st.form_submit_button("Guardar pago")
if sub:
    pay_row = {
        "account_id": sel,
        "amount": float(amount),
        "due_date": due.isoformat(),
        "period_label": period_label or None,
        "notes": notes or None,
        "status": "pagado" if mark_paid else "pendiente",
    }
    if mark_paid:
        from datetime import datetime, timezone

        pay_row["paid_at"] = datetime.now(timezone.utc).isoformat()
    sb.table("rental_payments").insert(pay_row).execute()
    if advance_next and mark_paid:
        base = due
        nxt = base + timedelta(days=7)
        sb.table("accounts").update({"rental_next_due_date": nxt.isoformat()}).eq("id", sel).execute()
    st.cache_data.clear()
    st.success("Pago registrado.")
    st.rerun()

st.subheader("Historial de pagos (cuenta seleccionada)")
hist = payments_for(sel)
st.dataframe(hist, use_container_width=True, hide_index=True)
