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

st.title("Cuentas por pagar")

if not supabase_configured():
    st.error("Configura Supabase.")
    st.stop()

require_roles(FINANCE_ROLES)
token = st.session_state.access_token
sb = get_client(token)

STATUS_OPTS = [
    ("pendiente", "Pendiente"),
    ("parcial", "Parcial"),
    ("pagado", "Pagado"),
    ("vencido", "Vencido"),
    ("cancelado", "Cancelado"),
]
STATUS_KEYS = [x[0] for x in STATUS_OPTS]
STATUS_LABEL = dict(STATUS_OPTS)


@st.cache_data(ttl=30)
def load_payables(_token: str):
    c = get_client(_token)
    r = c.table("accounts_payable").select("*").order("due_date", desc=False).execute()
    return r.data or []


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

try:
    rows = load_payables(token)
except Exception as e:
    st.error(f"Error al cargar: {e}")
    st.stop()

st.dataframe(rows, use_container_width=True, hide_index=True)

with st.expander("Registrar obligación por pagar"):
    with st.form("new_ap"):
        vendor = st.text_input("Proveedor *")
        category = st.text_input("Categoría")
        description = st.text_area("Descripción")
        amount = st.number_input("Monto *", min_value=0.01, value=100.0, step=1.0)
        currency = st.text_input("Moneda", value="USD")
        due = st.date_input("Vencimiento *", value=date.today())
        ref = st.text_input("Número de referencia")
        notes = st.text_area("Notas")
        sub = st.form_submit_button("Guardar")
    if sub:
        if not vendor.strip():
            st.warning("El proveedor es obligatorio.")
        else:
            try:
                sb.table("accounts_payable").insert(
                    {
                        "vendor_name": vendor.strip(),
                        "category": category or None,
                        "description": description or None,
                        "amount": float(amount),
                        "currency": (currency or "USD").strip() or "USD",
                        "due_date": due.isoformat(),
                        "status": "pendiente",
                        "reference_number": ref or None,
                        "notes": notes or None,
                    }
                ).execute()
                st.cache_data.clear()
                st.success("Registro creado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

if rows:
    st.subheader("Actualizar pago / estado")
    by_id = {r["id"]: r for r in rows}
    pid = st.selectbox("Seleccionar registro", options=list(by_id.keys()), format_func=lambda i: f"{by_id[i].get('vendor_name')} — ${by_id[i].get('amount')} — vence {by_id[i].get('due_date')}")
    cur = by_id[pid]
    try:
        st_ix = STATUS_KEYS.index(cur.get("status") or "pendiente")
    except ValueError:
        st_ix = 0
    with st.form("upd_ap"):
        paid_amt = st.number_input("Monto pagado (acumulado)", min_value=0.0, value=float(cur.get("paid_amount") or 0), step=1.0)
        paid_date = st.date_input("Fecha de pago (opcional)", value=None)
        new_st = st.selectbox("Estado", options=STATUS_KEYS, format_func=lambda x: STATUS_LABEL[x], index=st_ix)
        notes2 = st.text_area("Notas (reemplazan si escribís algo)", value=cur.get("notes") or "")
        save = st.form_submit_button("Guardar cambios")
    if save:
        payload = {
            "paid_amount": float(paid_amt),
            "status": new_st,
            "notes": notes2 or None,
        }
        if paid_date:
            payload["paid_at"] = paid_date.isoformat()
        try:
            sb.table("accounts_payable").update(payload).eq("id", pid).execute()
            st.cache_data.clear()
            st.success("Actualizado.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if can_delete_finance_records():
        st.subheader("Eliminar registro")
        if st.button("Eliminar seleccionado", type="primary"):
            try:
                sb.table("accounts_payable").delete().eq("id", pid).execute()
                st.cache_data.clear()
                st.success("Eliminado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
