import sys
from pathlib import Path
from datetime import date

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.db import get_client
from src.rbac import FINANCE_ROLES, can_delete_finance_records, require_roles

st.set_page_config(page_title="Por cobrar", layout="wide")
st.title("Cuentas por cobrar")

if not supabase_configured():
    st.error("Configura Supabase.")
    st.stop()

require_roles(FINANCE_ROLES)
token = st.session_state.access_token
sb = get_client(token)

STATUS_OPTS = [
    ("pendiente", "Pendiente"),
    ("parcial", "Parcial"),
    ("cobrado", "Cobrado (total)"),
    ("pagado", "Pagado (alias)"),
    ("vencido", "Vencido"),
    ("cancelado", "Cancelado"),
]
STATUS_KEYS = [x[0] for x in STATUS_OPTS]
STATUS_LABEL = dict(STATUS_OPTS)


@st.cache_data(ttl=30)
def load_receivables(_token: str):
    c = get_client(_token)
    r = c.table("accounts_receivable").select("*").order("due_date", desc=False).execute()
    return r.data or []


@st.cache_data(ttl=60)
def load_clients(_token: str):
    c = get_client(_token)
    r = c.table("clients").select("id,name").order("name").execute()
    return r.data or []


@st.cache_data(ttl=60)
def load_delivery_accounts(_token: str):
    c = get_client(_token)
    r = (
        c.table("accounts")
        .select("id, client_id, platform_id")
        .order("created_at", desc=True)
        .execute()
    )
    rows = r.data or []
    plats = {p["id"]: p["name"] for p in ((c.table("delivery_platforms").select("id,name").execute().data) or [])}
    for row in rows:
        row["_label"] = f"{plats.get(row.get('platform_id'), '?')} ({str(row['id'])[:8]}…)"
    return rows


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

try:
    rows = load_receivables(token)
    clients = load_clients(token)
    daccounts = load_delivery_accounts(token)
except Exception as e:
    st.error(f"Error al cargar: {e}")
    st.stop()

st.dataframe(rows, use_container_width=True, hide_index=True)

cid_map = {c["id"]: c["name"] for c in clients}

with st.expander("Registrar cobro esperado"):
    modo = st.radio("Tipo", ["Cliente en sistema", "Solo nombre / externo"], horizontal=True)
    with st.form("new_ar"):
        client_id = None
        counterparty = None
        if modo == "Cliente en sistema":
            if clients:
                client_id = st.selectbox("Cliente", options=[c["id"] for c in clients], format_func=lambda x: cid_map[x])
            else:
                st.warning("No hay clientes cargados; usá modo externo.")
        else:
            counterparty = st.text_input("Nombre del deudor / referencia *")
        description = st.text_area("Descripción")
        amount = st.number_input("Monto *", min_value=0.01, value=100.0, step=1.0)
        currency = st.text_input("Moneda", value="USD")
        due = st.date_input("Vencimiento *", value=date.today())
        ref = st.text_input("Número de referencia")
        rel_acc = st.selectbox(
            "Cuenta delivery relacionada (opcional)",
            options=[None] + [a["id"] for a in daccounts],
            format_func=lambda x: "—" if x is None else next((a["_label"] for a in daccounts if a["id"] == x), str(x)),
        )
        notes = st.text_area("Notas")
        sub = st.form_submit_button("Guardar")
    if sub:
        if modo == "Cliente en sistema" and not clients:
            st.error("Creá un cliente primero o usá modo externo.")
        elif modo == "Solo nombre / externo" and not (counterparty or "").strip():
            st.error("Indicá el nombre del deudor.")
        else:
            cid = client_id if modo == "Cliente en sistema" else None
            cparty = None if modo == "Cliente en sistema" else (counterparty.strip() if counterparty else None)
            try:
                sb.table("accounts_receivable").insert(
                    {
                        "client_id": cid,
                        "counterparty_name": cparty,
                        "description": description or None,
                        "amount": float(amount),
                        "currency": (currency or "USD").strip() or "USD",
                        "due_date": due.isoformat(),
                        "status": "pendiente",
                        "reference_number": ref or None,
                        "related_delivery_account_id": rel_acc,
                        "notes": notes or None,
                    }
                ).execute()
                st.cache_data.clear()
                st.success("Registro creado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

if rows:
    st.subheader("Actualizar cobro / estado")
    by_id = {r["id"]: r for r in rows}
    rid = st.selectbox(
        "Seleccionar registro",
        options=list(by_id.keys()),
        format_func=lambda i: f"{by_id[i].get('counterparty_name') or cid_map.get(by_id[i].get('client_id'), 'Cliente')} — ${by_id[i].get('amount')}",
    )
    cur = by_id[rid]
    try:
        st_ix = STATUS_KEYS.index(cur.get("status") or "pendiente")
    except ValueError:
        st_ix = 0
    with st.form("upd_ar"):
        recv_amt = st.number_input("Monto cobrado (acumulado)", min_value=0.0, value=float(cur.get("received_amount") or 0), step=1.0)
        recv_date = st.date_input("Fecha último cobro (opcional)", value=None)
        new_st = st.selectbox("Estado", options=STATUS_KEYS, format_func=lambda x: STATUS_LABEL[x], index=st_ix)
        notes2 = st.text_area("Notas", value=cur.get("notes") or "")
        save = st.form_submit_button("Guardar cambios")
    if save:
        payload = {
            "received_amount": float(recv_amt),
            "status": new_st,
            "notes": notes2 or None,
        }
        if recv_date:
            payload["received_at"] = recv_date.isoformat()
        try:
            sb.table("accounts_receivable").update(payload).eq("id", rid).execute()
            st.cache_data.clear()
            st.success("Actualizado.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if can_delete_finance_records():
        st.subheader("Eliminar registro")
        if st.button("Eliminar seleccionado", type="primary"):
            try:
                sb.table("accounts_receivable").delete().eq("id", rid).execute()
                st.cache_data.clear()
                st.success("Eliminado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
