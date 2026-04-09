import sys
from pathlib import Path
from datetime import date, timedelta

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

from src.config import supabase_configured
from src.constants import ACCOUNT_STATUS_LABELS, SALE_TYPE_LABELS, SERVICE_MODALITY_LABELS
from src.db import get_client
from src.rbac import require_login

st.title("Resumen gerencial")

if not supabase_configured():
    st.error("Configura Supabase en `.env` o Secrets.")
    st.stop()

require_login()
token = st.session_state.access_token


@st.cache_data(ttl=60)
def load_accounts(_token: str):
    sb = get_client(_token)
    r = sb.table("accounts").select(
        "id, status, sale_type, service_modality, delivered_at, rental_next_due_date, rental_weekly_amount, platform_id, client_id, technician_id"
    ).execute()
    return r.data or []


@st.cache_data(ttl=120)
def load_platforms(_token: str):
    sb = get_client(_token)
    r = sb.table("delivery_platforms").select("id, name, code").execute()
    return {row["id"]: row for row in (r.data or [])}


try:
    accounts = load_accounts(token)
    platforms = load_platforms(token)
except Exception as e:
    st.error(f"No se pudieron cargar los datos: {e}")
    st.stop()

if not accounts:
    st.info("Aún no hay cuentas. Crea clientes, técnicos y cuentas en las otras páginas.")
    st.stop()

df = pd.DataFrame(accounts)
df["status_label"] = df["status"].map(lambda s: ACCOUNT_STATUS_LABELS.get(s, s))
df["sale_label"] = df["sale_type"].map(lambda s: SALE_TYPE_LABELS.get(s, s))
df["platform_name"] = df["platform_id"].map(lambda pid: platforms.get(pid, {}).get("name", pid))
if "service_modality" not in df.columns:
    df["service_modality"] = "cuenta_nombre_tercero"
df["modality_label"] = df["service_modality"].apply(
    lambda m: SERVICE_MODALITY_LABELS.get(m or "cuenta_nombre_tercero", m)
)

today = date.today()
soon = today + timedelta(days=7)


def rental_alert(row):
    if row.get("sale_type") != "alquiler" or not row.get("rental_next_due_date"):
        return None
    d = row["rental_next_due_date"]
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if d < today:
        return "vencido"
    if d <= soon:
        return "próximo"
    return "ok"


df["rental_alert"] = df.apply(rental_alert, axis=1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total cuentas", len(df))
c2.metric("En alquiler", int((df["sale_type"] == "alquiler").sum()))
c3.metric("Entregadas", int((df["status"] == "entregada").sum()))
rent_due = df[df["rental_alert"].isin(["vencido", "próximo"])]
c4.metric("Alquileres a vigilar", len(rent_due))

st.subheader("Cuentas por estado")
status_counts = df["status_label"].value_counts()
st.bar_chart(status_counts)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Por plataforma")
    st.bar_chart(df["platform_name"].value_counts())
with col_b:
    st.subheader("Venta vs alquiler")
    st.bar_chart(df["sale_label"].value_counts())

st.subheader("Por modalidad de servicio")
st.caption("Tercero vs licencia sin SSN vs licencia + SSN (activación por cupo).")
st.bar_chart(df["modality_label"].value_counts())

st.subheader("Alertas de alquiler (vencido o próxima semana)")
alert_df = df[df["rental_alert"].isin(["vencido", "próximo"])][
    ["platform_name", "status_label", "sale_label", "rental_next_due_date", "rental_weekly_amount", "rental_alert"]
]
if alert_df.empty:
    st.success("Sin alertas de vencimiento en los próximos 7 días.")
else:
    st.dataframe(alert_df, use_container_width=True, hide_index=True)

st.caption("Los datos se actualizan cada ~60 s (caché Streamlit).")
