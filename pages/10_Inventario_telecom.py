import sys
from pathlib import Path
from datetime import date
import json

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.db import get_client
from src.rbac import can_edit_telecom_inventory, require_login

st.set_page_config(page_title="Inventario telecom", layout="wide")
st.title("Inventario telecom y números (EE. UU.)")

if not supabase_configured():
    st.error("Configura Supabase.")
    st.stop()

require_login()
token = st.session_state.access_token
sb = get_client(token)
edit_ok = can_edit_telecom_inventory()

TYPE_OPTS = [
    ("datos", "Plan de datos / eSIM"),
    ("numero_telefonico", "Número comprado en web (SMS / verificación)"),
    ("proxy", "Proxy"),
    ("linea_telefonica", "Línea / VoIP (si aplica)"),
]
TYPE_KEYS = [x[0] for x in TYPE_OPTS]
TYPE_LABEL = dict(TYPE_OPTS)

STATUS_OPTS = [
    ("activo", "Activo"),
    ("suspendido", "Suspendido"),
    ("vencido", "Vencido"),
    ("reserva", "Reserva"),
]
STATUS_KEYS = [x[0] for x in STATUS_OPTS]
STATUS_LABEL = dict(STATUS_OPTS)

st.caption(
    "Registrá números comprados en sitios de EE. UU. como tipo **Número comprado en web**. "
    "No guardes contraseñas en texto plano: usá **referencia al vault** o notas generales."
)


@st.cache_data(ttl=30)
def load_telecom(_token: str):
    c = get_client(_token)
    r = c.table("telecom_resources").select("*").order("created_at", desc=True).execute()
    return r.data or []


@st.cache_data(ttl=60)
def load_technicians(_token: str):
    c = get_client(_token)
    r = c.table("technicians").select("id,name,active").eq("active", True).order("name").execute()
    return r.data or []


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

try:
    rows = load_telecom(token)
    techs = load_technicians(token)
except Exception as e:
    st.error(f"Error al cargar: {e}")
    st.stop()

ft = st.multiselect(
    "Filtrar por tipo",
    options=TYPE_KEYS,
    format_func=lambda x: TYPE_LABEL[x],
    default=TYPE_KEYS,
)
view = [r for r in rows if r.get("resource_type") in ft] if ft else rows
st.dataframe(view, use_container_width=True, hide_index=True)

tid_map = {t["id"]: t["name"] for t in techs}

if edit_ok:
    with st.expander("Alta de recurso"):
        with st.form("new_tr"):
            rt = st.selectbox("Tipo", options=TYPE_KEYS, format_func=lambda x: TYPE_LABEL[x])
            label = st.text_input("Nombre / uso interno *")
            provider = st.text_input("Sitio o proveedor (ej. página donde compraste el número)")
            identifier = st.text_input("Identificador (+1…, host:puerto, ICCID…)")
            vault_ref = st.text_input("Referencia vault (opcional)", help="ID o path en tu gestor de secretos")
            monthly = st.number_input("Costo mensual (opcional)", min_value=0.0, value=0.0, step=1.0)
            investment = st.number_input("Inversión inicial (opcional)", min_value=0.0, value=0.0, step=1.0)
            start_d = st.date_input("Inicio (opcional)", value=None)
            renew_d = st.date_input("Renovación / vencimiento (opcional)", value=None)
            st_v = st.selectbox("Estado", options=STATUS_KEYS, format_func=lambda x: STATUS_LABEL[x])
            tech_id = st.selectbox(
                "Asignar a técnico (opcional)",
                options=[None] + [t["id"] for t in techs],
                format_func=lambda x: "—" if x is None else tid_map.get(x, str(x)),
            )
            meta_txt = st.text_area("Metadata JSON (opcional)", value="{}")
            notes = st.text_area("Notas")
            sub = st.form_submit_button("Guardar")
        if sub:
            if not label.strip():
                st.warning("El nombre es obligatorio.")
            else:
                try:
                    meta = json.loads(meta_txt.strip() or "{}")
                except json.JSONDecodeError:
                    st.error("Metadata debe ser JSON válido.")
                else:
                    payload = {
                        "resource_type": rt,
                        "label": label.strip(),
                        "provider": provider or None,
                        "identifier": identifier or None,
                        "credentials_vault_ref": vault_ref or None,
                        "monthly_cost": float(monthly) if monthly else None,
                        "initial_investment": float(investment) if investment else None,
                        "start_date": start_d.isoformat() if start_d else None,
                        "renewal_date": renew_d.isoformat() if renew_d else None,
                        "status": st_v,
                        "technician_id": tech_id,
                        "metadata": meta,
                        "notes": notes or None,
                    }
                    try:
                        sb.table("telecom_resources").insert(payload).execute()
                        st.cache_data.clear()
                        st.success("Recurso creado.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    if rows:
        st.subheader("Editar o eliminar")
        by_id = {r["id"]: r for r in rows}
        pick = st.selectbox(
            "Recurso",
            options=list(by_id.keys()),
            format_func=lambda i: f"{by_id[i].get('label')} ({TYPE_LABEL.get(by_id[i].get('resource_type'), by_id[i].get('resource_type'))})",
        )
        cur = by_id[pick]
        try:
            t_ix = TYPE_KEYS.index(cur.get("resource_type") or "numero_telefonico")
        except ValueError:
            t_ix = 1
        try:
            s_ix = STATUS_KEYS.index(cur.get("status") or "activo")
        except ValueError:
            s_ix = 0
        sd = cur.get("start_date")
        rd = cur.get("renewal_date")
        with st.form("upd_tr"):
            rt = st.selectbox("Tipo", options=TYPE_KEYS, format_func=lambda x: TYPE_LABEL[x], index=t_ix)
            label = st.text_input("Nombre", value=cur.get("label") or "")
            provider = st.text_input("Proveedor / sitio", value=cur.get("provider") or "")
            identifier = st.text_input("Identificador", value=cur.get("identifier") or "")
            vault_ref = st.text_input("Vault ref", value=cur.get("credentials_vault_ref") or "")
            monthly = st.number_input("Costo mensual", min_value=0.0, value=float(cur.get("monthly_cost") or 0), step=1.0)
            investment = st.number_input("Inversión inicial", min_value=0.0, value=float(cur.get("initial_investment") or 0), step=1.0)
            start_d = st.date_input(
                "Inicio",
                value=date.fromisoformat(str(sd)[:10]) if sd else None,
            )
            renew_d = st.date_input(
                "Renovación",
                value=date.fromisoformat(str(rd)[:10]) if rd else None,
            )
            st_v = st.selectbox("Estado", options=STATUS_KEYS, format_func=lambda x: STATUS_LABEL[x], index=s_ix)
            topts = [None] + [t["id"] for t in techs]
            try:
                tix = topts.index(cur.get("technician_id"))
            except ValueError:
                tix = 0
            tech_id = st.selectbox(
                "Técnico",
                options=topts,
                format_func=lambda x: "—" if x is None else tid_map.get(x, str(x)),
                index=tix,
            )
            meta_txt = st.text_area("Metadata JSON", value=json.dumps(cur.get("metadata") or {}, ensure_ascii=False, indent=2))
            notes = st.text_area("Notas", value=cur.get("notes") or "")
            save = st.form_submit_button("Guardar cambios")
        if save:
            try:
                meta = json.loads(meta_txt.strip() or "{}")
            except json.JSONDecodeError:
                st.error("JSON inválido.")
            else:
                payload = {
                    "resource_type": rt,
                    "label": label.strip(),
                    "provider": provider or None,
                    "identifier": identifier or None,
                    "credentials_vault_ref": vault_ref or None,
                    "monthly_cost": float(monthly) if monthly else None,
                    "initial_investment": float(investment) if investment else None,
                    "start_date": start_d.isoformat() if start_d else None,
                    "renewal_date": renew_d.isoformat() if renew_d else None,
                    "status": st_v,
                    "technician_id": tech_id,
                    "metadata": meta,
                    "notes": notes or None,
                }
                try:
                    sb.table("telecom_resources").update(payload).eq("id", pick).execute()
                    st.cache_data.clear()
                    st.success("Actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        if st.button("Eliminar recurso", type="primary"):
            try:
                sb.table("telecom_resources").delete().eq("id", pick).execute()
                st.cache_data.clear()
                st.success("Eliminado.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
else:
    st.info("Solo **administración** y **super usuario** pueden dar de alta o editar inventario. Vos podés ver lo que permita tu rol.")
