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

st.title("Gastos operativos")

if not supabase_configured():
    st.error("Configura Supabase.")
    st.stop()

require_roles(FINANCE_ROLES)
token = st.session_state.access_token
sb = get_client(token)


@st.cache_data(ttl=30)
def load_expenses(_token: str):
    c = get_client(_token)
    r = c.table("operational_expenses").select("*").order("expense_date", desc=True).execute()
    return r.data or []


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

try:
    rows = load_expenses(token)
except Exception as e:
    st.error(f"Error al cargar: {e}")
    st.stop()

st.dataframe(rows, use_container_width=True, hide_index=True)

with st.expander("Registrar gasto"):
    with st.form("new_ox"):
        category = st.text_input("Categoría *", placeholder="Oficina, Software, Legal…")
        vendor = st.text_input("Proveedor")
        description = st.text_area("Descripción")
        amount = st.number_input("Monto *", min_value=0.01, value=50.0, step=1.0)
        currency = st.text_input("Moneda", value="USD")
        exp_date = st.date_input("Fecha del gasto", value=date.today())
        pay_method = st.text_input("Medio de pago", placeholder="tarjeta, transferencia…")
        receipt = st.text_input("Ref. comprobante / factura")
        notes = st.text_area("Notas")
        sub = st.form_submit_button("Guardar")
    if sub:
        if not category.strip():
            st.warning("La categoría es obligatoria.")
        else:
            try:
                sb.table("operational_expenses").insert(
                    {
                        "category": category.strip(),
                        "vendor_name": vendor or None,
                        "description": description or None,
                        "amount": float(amount),
                        "currency": (currency or "USD").strip() or "USD",
                        "expense_date": exp_date.isoformat(),
                        "payment_method": pay_method or None,
                        "receipt_ref": receipt or None,
                        "notes": notes or None,
                    }
                ).execute()
                st.cache_data.clear()
                st.success("Gasto registrado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

if rows:
    st.subheader("Editar gasto")
    by_id = {r["id"]: r for r in rows}
    eid = st.selectbox(
        "Seleccionar",
        options=list(by_id.keys()),
        format_func=lambda i: f"{by_id[i].get('category')} — ${by_id[i].get('amount')} — {by_id[i].get('expense_date')}",
    )
    cur = by_id[eid]
    with st.form("upd_ox"):
        category = st.text_input("Categoría", value=cur.get("category") or "")
        vendor = st.text_input("Proveedor", value=cur.get("vendor_name") or "")
        description = st.text_area("Descripción", value=cur.get("description") or "")
        amount = st.number_input("Monto", min_value=0.01, value=float(cur.get("amount") or 0), step=1.0)
        currency = st.text_input("Moneda", value=cur.get("currency") or "USD")
        exp_date = st.date_input("Fecha", value=date.fromisoformat(str(cur["expense_date"])[:10]) if cur.get("expense_date") else date.today())
        pay_method = st.text_input("Medio de pago", value=cur.get("payment_method") or "")
        receipt = st.text_input("Ref. comprobante", value=cur.get("receipt_ref") or "")
        notes = st.text_area("Notas", value=cur.get("notes") or "")
        save = st.form_submit_button("Guardar cambios")
    if save:
        try:
            sb.table("operational_expenses").update(
                {
                    "category": category.strip(),
                    "vendor_name": vendor or None,
                    "description": description or None,
                    "amount": float(amount),
                    "currency": (currency or "USD").strip(),
                    "expense_date": exp_date.isoformat(),
                    "payment_method": pay_method or None,
                    "receipt_ref": receipt or None,
                    "notes": notes or None,
                }
            ).eq("id", eid).execute()
            st.cache_data.clear()
            st.success("Actualizado.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if can_delete_finance_records():
        if st.button("Eliminar gasto seleccionado", type="primary"):
            try:
                sb.table("operational_expenses").delete().eq("id", eid).execute()
                st.cache_data.clear()
                st.success("Eliminado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
