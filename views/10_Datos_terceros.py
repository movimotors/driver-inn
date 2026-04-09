import sys
from collections import Counter
from datetime import date
from io import BytesIO
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.constants import (
    TPI_DATA_SEMAPHORE_COLOR,
    TPI_DATA_SEMAPHORE_HELP,
    TPI_DATA_SEMAPHORE_LABELS,
    TPI_DATA_SEMAPHORE_ORDER,
    TPI_INVENTORY_BUCKET_COLOR,
    TPI_INVENTORY_BUCKET_LABELS,
    TPI_WORKFLOW_LABELS,
    TPI_WORKFLOW_ORDER,
)
from src.db import get_client
from src.tpi_account_linking import inventory_bucket
from src.rbac import can_delete_datos_terceros, can_edit_datos_terceros, require_login
from src.storage_api import storage_download, storage_remove, storage_upload

st.title("Datos terceros (licencias)")

if not supabase_configured():
    st.error("Configura Supabase.")
    st.stop()

require_login()
token = st.session_state.access_token
sb = get_client(token)
edit_ok = can_edit_datos_terceros()
delete_ok = can_delete_datos_terceros()

LICENSE_STATUS_OPTS = [
    ("vigente", "Vigente"),
    ("por_vencer", "Por vencer"),
    ("vencida", "Vencida"),
    ("suspendida", "Suspendida"),
    ("revocada", "Revocada / cancelada"),
    ("en_tramite", "En trámite"),
]
STATUS_KEYS = [x[0] for x in LICENSE_STATUS_OPTS]
STATUS_LABEL = dict(LICENSE_STATUS_OPTS)

SEM_KEYS = list(TPI_DATA_SEMAPHORE_ORDER)
SEM_LABEL = TPI_DATA_SEMAPHORE_LABELS

PLATFORM_FIELDS = [
    ("use_doordash", "DoorDash"),
    ("use_instacart", "Instacart"),
    ("use_lyft", "Lyft Driver"),
    ("use_ubereats", "Uber Eats"),
    ("use_spark_driver", "Spark Driver"),
    ("use_amazon_flex", "Amazon Flex"),
    ("use_veho", "Veho"),
    ("use_other", "Otra plataforma"),
]


def _card_start(title: str, hint: str | None = None) -> None:
    """Encabezado dentro de un contenedor con borde (tarjeta)."""
    st.markdown(f"##### {title}")
    if hint:
        st.caption(hint)


def _platform_labels_row(row: dict) -> str:
    parts = [lbl for key, lbl in PLATFORM_FIELDS if row.get(key)]
    return ", ".join(parts) if parts else "—"


def _is_dato_malo(row: dict) -> bool:
    return row.get("data_semaphore") == "background_malo"


@st.cache_data(ttl=30)
def load_identities(_token: str):
    c = get_client(_token)
    r = c.table("third_party_identities").select("*").order("created_at", desc=True).execute()
    return r.data or []


@st.cache_data(ttl=30)
def load_links_by_identity(_token: str):
    c = get_client(_token)
    r = c.table("account_identity_links").select("identity_id,account_id").execute()
    out: dict[str, list[str]] = {}
    for row in r.data or []:
        iid = row.get("identity_id")
        aid = row.get("account_id")
        if not iid or not aid:
            continue
        out.setdefault(str(iid), []).append(str(aid))
    return out


@st.cache_data(ttl=30)
def load_account_choices(_token: str):
    c = get_client(_token)
    acc = (c.table("accounts").select("id,client_id,platform_id").execute().data) or []
    clients = {x["id"]: x.get("name") for x in (c.table("clients").select("id,name").execute().data or [])}
    plats = {x["id"]: x for x in (c.table("delivery_platforms").select("id,name,code").execute().data or [])}
    choices = []
    for a in acc:
        cid = a.get("client_id")
        pid = a.get("platform_id")
        cn = clients.get(cid, "?")
        p = plats.get(pid, {})
        pl = p.get("name") or p.get("code") or "?"
        short = str(a["id"])[:8]
        choices.append((a["id"], f"{cn} · {pl} · …{short}"))
    return choices


@st.cache_data(ttl=60)
def load_client_choices(_token: str):
    c = get_client(_token)
    rows = (c.table("clients").select("id,name").order("name").execute().data) or []
    return [(x["id"], x.get("name") or "—") for x in rows]


@st.cache_data(ttl=60)
def load_technician_choices(_token: str):
    c = get_client(_token)
    rows = (
        c.table("technicians").select("id,name").eq("active", True).order("name").execute().data
        or []
    )
    return [(x["id"], x.get("name") or "—") for x in rows]


def _show_license_photo(label: str, path: str | None):
    if not path:
        st.caption("Sin archivo cargado." if not label else f"{label}: sin archivo")
        return
    try:
        data = storage_download(token, path)
        if label:
            st.caption(label)
        st.image(BytesIO(data), use_container_width=True)
    except Exception as e:
        st.warning(f"{label + ': ' if label else ''}No se pudo mostrar ({e})")


def _delete_photos_if_any(row: dict):
    for key in ("photo_front_path", "photo_back_path", "portrait_photo_path"):
        p = row.get(key)
        if p:
            try:
                storage_remove(token, p)
            except Exception:
                pass


def _payload_from_form(
    first_name: str,
    last_name: str,
    address: str,
    lic_num: str,
    lic_status: str,
    issuing_state: str,
    dob,
    issued,
    expires,
    notes: str,
    platforms: dict[str, bool],
    extra: dict | None = None,
) -> dict:
    d = {
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "address_line": address.strip() or None,
        "license_number": lic_num.strip(),
        "license_status": lic_status,
        "license_issuing_state": issuing_state.strip() or None,
        "date_of_birth": dob.isoformat() if dob else None,
        "license_issued_date": issued.isoformat() if issued else None,
        "license_expiry_date": expires.isoformat() if expires else None,
        "notes": notes.strip() or None,
        **platforms,
    }
    if extra:
        d.update(extra)
    return d


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

try:
    rows = load_identities(token)
    links_map = load_links_by_identity(token)
    acct_choices = load_account_choices(token)
    client_opts = load_client_choices(token)
    tech_opts = load_technician_choices(token)
except Exception as e:
    st.error(f"Error al cargar datos: {e}")
    st.info(
        "¿Ejecutaste **migration_005** (tabla + Storage) y **migration_007** (cliente, técnico, flujo y semáforo)?"
    )
    st.stop()

acct_label = dict(acct_choices)
cid_list = [x[0] for x in client_opts]
cid_lab = dict(client_opts)
tid_list = [x[0] for x in tech_opts]
tid_lab = dict(tech_opts)

st.caption(
    "Este módulo es el **inventario** de licencias de terceros: ves qué fichas están **disponibles**, "
    "cuáles ya están **asignadas** a una cuenta delivery y cuáles están **bloqueadas (dato malo)**. "
    "La **asignación a la cuenta** se hace en **Cuentas** o en **Clientes → Nueva cuenta delivery**, "
    "elegiendo modalidad *Cuenta a nombre de tercero* y la ficha disponible. "
    "El **tablero Kanban** sigue el trámite con cliente y técnico."
)

# --- Resumen inventario (tarjetas) ---
_bucket_counts = Counter(inventory_bucket(r, str(r["id"]), links_map) for r in rows)
b1, b2, b3 = st.columns(3)
with b1:
    with st.container(border=True):
        st.markdown(
            f"<div style='color:{TPI_INVENTORY_BUCKET_COLOR['disponible']};font-size:1.6rem;font-weight:700;'>"
            f"{_bucket_counts.get('disponible', 0)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{TPI_INVENTORY_BUCKET_LABELS['disponible']}**")
        st.caption("Listos para vincular desde Cuentas / Clientes.")
with b2:
    with st.container(border=True):
        st.markdown(
            f"<div style='color:{TPI_INVENTORY_BUCKET_COLOR['asignado']};font-size:1.6rem;font-weight:700;'>"
            f"{_bucket_counts.get('asignado', 0)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{TPI_INVENTORY_BUCKET_LABELS['asignado']}**")
        st.caption("Ya tienen vínculo con al menos una cuenta.")
with b3:
    with st.container(border=True):
        st.markdown(
            f"<div style='color:{TPI_INVENTORY_BUCKET_COLOR['malo']};font-size:1.6rem;font-weight:700;'>"
            f"{_bucket_counts.get('malo', 0)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{TPI_INVENTORY_BUCKET_LABELS['malo']}**")
        st.caption("No reutilizar; el sistema bloquea nuevos vínculos.")

malo_rows = [r for r in rows if _is_dato_malo(r)]
if malo_rows:
    st.error(
        f"**Alerta · Dato malo:** {len(malo_rows)} registro(s) con **Background malo** — "
        "no deben usarse en cuentas nuevas. Revisá el listado abajo."
    )
    with st.container(border=True):
        _card_start("Listado · datos bloqueados (Background malo)", "Solo lectura operativa; rehabilitá el semáforo solo si hubo error.")
        for mr in malo_rows:
            with st.container(border=True):
                st.markdown(
                    f"**{mr.get('first_name', '')} {mr.get('last_name', '')}** · `{mr.get('license_number', '')}`"
                )
                st.caption(
                    f"Cliente: {cid_lab.get(str(mr.get('request_client_id')), '—')} · "
                    f"Técnico: {tid_lab.get(str(mr.get('assigned_technician_id')), '—')}"
                )

# --- Tabla resumen ---
summary = []
for r in rows:
    iid = str(r["id"])
    accs = links_map.get(iid, [])
    acc_lbl = ", ".join(acct_label.get(a, str(a)[:8]) for a in accs[:3])
    if len(accs) > 3:
        acc_lbl += f" (+{len(accs) - 3})"
    inv_key = inventory_bucket(r, iid, links_map)
    summary.append(
        {
            "Inventario": TPI_INVENTORY_BUCKET_LABELS.get(inv_key, inv_key),
            "Nombre": f"{r.get('first_name', '')} {r.get('last_name', '')}".strip(),
            "Nº licencia": r.get("license_number"),
            "Cliente sol.": cid_lab.get(str(r.get("request_client_id")), "—"),
            "Técnico": tid_lab.get(str(r.get("assigned_technician_id")), "—"),
            "Flujo": TPI_WORKFLOW_LABELS.get(r.get("workflow_status"), r.get("workflow_status") or "—"),
            "Semáforo": SEM_LABEL.get(r.get("data_semaphore"), r.get("data_semaphore") or "—"),
            "Estado lic.": STATUS_LABEL.get(r.get("license_status"), r.get("license_status")),
            "Vence": str(r.get("license_expiry_date") or "")[:10],
            "Plataformas": _platform_labels_row(r),
            "Cuentas": acc_lbl or "—",
            "_id": iid,
        }
    )
st.subheader("Listado")
with st.container(border=True):
    st.caption("Vista rápida: inventario, solicitud, equipo, flujo, semáforo y cuentas vinculadas (desde Cuentas).")
    st.dataframe(
        [{k: v for k, v in s.items() if k != "_id"} for s in summary],
        use_container_width=True,
        hide_index=True,
    )

# --- Detalle: fotos y cuentas ---
st.subheader("Detalle y fotos")
if not rows:
    st.info("Todavía no hay registros." + (" Usá el formulario de alta abajo." if edit_ok else ""))
else:
    by_id = {str(r["id"]): r for r in rows}
    pick = st.selectbox(
        "Elegí un registro para ver fotos y cuentas",
        options=list(by_id.keys()),
        format_func=lambda i: f"{by_id[i].get('first_name')} {by_id[i].get('last_name')} — {by_id[i].get('license_number')}",
    )
    cur = by_id[pick]
    with st.container(border=True):
        _card_start("Solicitud y control del dato")
        c_sem = TPI_DATA_SEMAPHORE_COLOR.get(cur.get("data_semaphore"), "#757575")
        st.markdown(
            f"**Cliente (solicitud):** {cid_lab.get(str(cur.get('request_client_id')), '—')} · "
            f"**Técnico:** {tid_lab.get(str(cur.get('assigned_technician_id')), '—')}"
        )
        st.markdown(
            f"**Flujo:** {TPI_WORKFLOW_LABELS.get(cur.get('workflow_status'), cur.get('workflow_status') or '—')} · "
            f"<span style='color:{c_sem};font-weight:600;'>Semáforo: "
            f"{SEM_LABEL.get(cur.get('data_semaphore'), cur.get('data_semaphore') or '—')}</span>",
            unsafe_allow_html=True,
        )
        if _is_dato_malo(cur):
            st.error("Este dato está **bloqueado (Background malo)** — no se asigna a más cuentas.")
    ph1, ph2 = st.columns(2)
    with ph1:
        with st.container(border=True):
            _card_start("📷 Frente de la licencia")
            _show_license_photo("", cur.get("photo_front_path"))
    with ph2:
        with st.container(border=True):
            _card_start("📷 Dorso de la licencia")
            _show_license_photo("", cur.get("photo_back_path"))
    with st.container(border=True):
        _card_start("🪪 Foto de rostro (tipo carnet)", "Obligatoria para usar este dato en cuentas a nombre de tercero.")
        _show_license_photo("", cur.get("portrait_photo_path"))
    with st.container(border=True):
        _card_start("🔗 Cuentas delivery vinculadas", "Donde se usa esta identidad.")
        la = links_map.get(pick, [])
        if la:
            for a in la:
                st.write(f"· {acct_label.get(a, a)}")
        else:
            st.caption("Ninguna cuenta vinculada todavía.")

# --- Alta ---
if edit_ok:
    with st.expander("➕ Nueva licencia / datos terceros", expanded=not rows):
        with st.form("new_id"):
            with st.container(border=True):
                _card_start(
                    "0 · Solicitud y equipo",
                    "**Cliente** que encarga el trámite y **técnico** que lo ejecuta (podés dejar técnico sin asignar al inicio).",
                )
                if not cid_list:
                    st.warning("Creá al menos un **cliente** en la pantalla Clientes.")
                n_req_client = st.selectbox(
                    "Cliente que hace la solicitud *",
                    options=cid_list,
                    format_func=lambda x: cid_lab.get(x, str(x)),
                    help="Quien contrata / pide el uso del dato de tercero.",
                )
                topts = [None] + tid_list
                n_tech = st.selectbox(
                    "Técnico asignado",
                    options=topts,
                    format_func=lambda x: "— Todavía sin asignar —" if x is None else tid_lab.get(x, str(x)),
                    help="Quien procesa la solicitud en campo; luego puede mover el tablero Kanban.",
                )
                n_sem = st.selectbox(
                    "Semáforo del dato",
                    options=SEM_KEYS,
                    format_func=lambda x: SEM_LABEL[x],
                    index=SEM_KEYS.index("revisar"),
                )
                st.caption(TPI_DATA_SEMAPHORE_HELP.get(n_sem, ""))
                wf_default = "asignada" if n_tech else "solicitud"
                try:
                    wf_ix = TPI_WORKFLOW_ORDER.index(wf_default)
                except ValueError:
                    wf_ix = 0
                n_wf = st.selectbox(
                    "Estado del flujo (Kanban)",
                    options=list(range(len(TPI_WORKFLOW_ORDER))),
                    format_func=lambda i: TPI_WORKFLOW_LABELS[TPI_WORKFLOW_ORDER[i]],
                    index=wf_ix,
                )

            with st.container(border=True):
                _card_start("1 · Datos de la persona", "Como figuran en el documento o licencia.")
                c_a, c_b = st.columns(2)
                with c_a:
                    n_fn = st.text_input("Nombre *", placeholder="Ej. María")
                with c_b:
                    n_ln = st.text_input("Apellido *", placeholder="Ej. García")
                n_addr = st.text_area("Dirección completa", placeholder="Calle, ciudad, estado, ZIP…", height=88)
                n_dob = st.date_input("Fecha de nacimiento (opcional)", value=None)

            with st.container(border=True):
                _card_start("2 · Datos de la licencia", "Número, estado de validez y fechas.")
                n_lic = st.text_input("Número de licencia *", placeholder="Según el plástico")
                r1, r2 = st.columns(2)
                with r1:
                    n_st = st.selectbox(
                        "Estado de la licencia",
                        options=STATUS_KEYS,
                        format_func=lambda x: STATUS_LABEL[x],
                        help="Vigente, vencida, en trámite, etc.",
                    )
                with r2:
                    n_iss_st = st.text_input(
                        "Estado emisor (EE. UU.)",
                        max_chars=4,
                        placeholder="FL, TX, CA…",
                        help="Abreviatura del estado que emitió la licencia.",
                    )
                d1, d2, d3 = st.columns(3)
                with d1:
                    n_iss_d = st.date_input("Fecha de emisión (opcional)", value=None)
                with d2:
                    n_exp = st.date_input("Fecha de expiración *", value=date.today())
                with d3:
                    st.caption("Revisá que la fecha de vencimiento coincida con la foto.")

            with st.container(border=True):
                _card_start("3 · Plataformas", "Marcá en cuáles se va a usar esta identidad.")
                plat_vals = {}
                p_row1 = st.columns(4)
                p_row2 = st.columns(4)
                for i, (field, lbl) in enumerate(PLATFORM_FIELDS):
                    box = p_row1[i] if i < 4 else p_row2[i - 4]
                    with box:
                        plat_vals[field] = st.checkbox(lbl, key=f"n_{field}")

            with st.container(border=True):
                _card_start("4 · Fotos", "JPEG, PNG o WebP. Hasta ~5 MB por archivo.")
                f1, f2, f3 = st.columns(3)
                with f1:
                    up_f = st.file_uploader("Licencia · Frente", type=["jpg", "jpeg", "png", "webp"], key="nf")
                with f2:
                    up_b = st.file_uploader("Licencia · Dorso", type=["jpg", "jpeg", "png", "webp"], key="nb")
                with f3:
                    up_portrait = st.file_uploader("Rostro (tipo carnet) *", type=["jpg", "jpeg", "png", "webp"], key="np")

            with st.container(border=True):
                _card_start(
                    "5 · Notas (sin vínculo a cuentas aquí)",
                    "El inventario se carga acá; **la cuenta** se asocia en **Cuentas** o **Clientes → Nueva cuenta delivery** "
                    "al elegir modalidad **Cuenta a nombre de tercero** y una ficha **disponible**.",
                )
                st.info(
                    "No se vinculan cuentas en esta pantalla: así el control queda claro "
                    "(disponible vs asignado) y coincide con el flujo de venta por cliente."
                )
                n_notes = st.text_area("Notas internas (opcional)", placeholder="Observaciones solo para el equipo…", height=100)

            sub = st.form_submit_button("Guardar registro", type="primary", use_container_width=True)
        if sub:
            if not n_fn.strip() or not n_ln.strip() or not n_lic.strip():
                st.error("Nombre, apellido y número de licencia son obligatorios.")
            elif not cid_list:
                st.error("Necesitás un cliente en el sistema para registrar la solicitud.")
            elif not n_req_client:
                st.error("Elegí el cliente que hace la solicitud.")
            elif not n_exp:
                st.error("Indicá fecha de expiración.")
            else:
                extra_new = {
                    "request_client_id": n_req_client,
                    "assigned_technician_id": n_tech,
                    "data_semaphore": n_sem,
                    "workflow_status": TPI_WORKFLOW_ORDER[n_wf],
                }
                payload = _payload_from_form(
                    n_fn,
                    n_ln,
                    n_addr,
                    n_lic,
                    n_st,
                    n_iss_st,
                    n_dob,
                    n_iss_d,
                    n_exp,
                    n_notes,
                    plat_vals,
                    extra=extra_new,
                )
                try:
                    ins = sb.table("third_party_identities").insert(payload).execute()
                    new_id = str(ins.data[0]["id"])
                    ext_f = "jpg"
                    if up_f:
                        ext_f = (up_f.name.rsplit(".", 1)[-1] if "." in up_f.name else "jpg").lower()
                        if ext_f == "jpeg":
                            ext_f = "jpg"
                        pf = f"{new_id}/front.{ext_f}"
                        storage_upload(token, pf, up_f.getvalue(), up_f.type or "image/jpeg")
                        sb.table("third_party_identities").update({"photo_front_path": pf}).eq("id", new_id).execute()
                    if up_b:
                        ext_b = (up_b.name.rsplit(".", 1)[-1] if "." in up_b.name else "jpg").lower()
                        if ext_b == "jpeg":
                            ext_b = "jpg"
                        pb = f"{new_id}/back.{ext_b}"
                        storage_upload(token, pb, up_b.getvalue(), up_b.type or "image/jpeg")
                        sb.table("third_party_identities").update({"photo_back_path": pb}).eq("id", new_id).execute()
                        if up_portrait:
                            ext_p = (up_portrait.name.rsplit(".", 1)[-1] if "." in up_portrait.name else "jpg").lower()
                            if ext_p == "jpeg":
                                ext_p = "jpg"
                            pp = f"{new_id}/portrait.{ext_p}"
                            storage_upload(token, pp, up_portrait.getvalue(), up_portrait.type or "image/jpeg")
                            sb.table("third_party_identities").update({"portrait_photo_path": pp}).eq("id", new_id).execute()
                    st.cache_data.clear()
                    st.success("Registro creado en inventario. Vinculá la cuenta desde **Cuentas** o **Clientes**.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

# --- Edición / baja ---
if edit_ok and rows:
    with st.expander("✏️ Editar o eliminar registro"):
        by_id = {str(r["id"]): r for r in rows}
        e_pick = st.selectbox(
            "Registro a modificar",
            options=list(by_id.keys()),
            format_func=lambda i: f"{by_id[i].get('first_name')} {by_id[i].get('last_name')} — {by_id[i].get('license_number')}",
            key="edit_pick",
        )
        cur = by_id[e_pick]
        try:
            st_ix = STATUS_KEYS.index(cur.get("license_status") or "vigente")
        except ValueError:
            st_ix = 0
        try:
            u_sem_ix = SEM_KEYS.index(cur.get("data_semaphore") or "revisar")
        except ValueError:
            u_sem_ix = 1
        try:
            u_wf_ix = TPI_WORKFLOW_ORDER.index(cur.get("workflow_status") or "solicitud")
        except ValueError:
            u_wf_ix = 0
        cu_blocked = _is_dato_malo(cur)

        def _ix_in(lst, val):
            try:
                return lst.index(val)
            except (ValueError, TypeError):
                return 0

        with st.form("upd_id"):
            with st.container(border=True):
                _card_start(
                    "0 · Solicitud y equipo",
                    "Actualizá cliente, técnico, flujo y semáforo. **Background malo** quita los vínculos a cuentas (desde la BD). "
                    "Los vínculos nuevos solo se gestionan en **Cuentas** / **Clientes**.",
                )
                u_req_client = st.selectbox(
                    "Cliente que hace la solicitud *",
                    options=cid_list,
                    index=_ix_in(cid_list, cur.get("request_client_id")),
                    format_func=lambda x: cid_lab.get(x, str(x)),
                )
                utopts = [None] + tid_list
                u_tech = st.selectbox(
                    "Técnico asignado",
                    options=utopts,
                    index=_ix_in(utopts, cur.get("assigned_technician_id")),
                    format_func=lambda x: "— Sin asignar —" if x is None else tid_lab.get(x, str(x)),
                )
                u_sem = st.selectbox(
                    "Semáforo del dato",
                    options=SEM_KEYS,
                    format_func=lambda x: SEM_LABEL[x],
                    index=u_sem_ix,
                )
                st.caption(TPI_DATA_SEMAPHORE_HELP.get(u_sem, ""))
                u_wf = st.selectbox(
                    "Estado del flujo (Kanban)",
                    options=list(range(len(TPI_WORKFLOW_ORDER))),
                    format_func=lambda i: TPI_WORKFLOW_LABELS[TPI_WORKFLOW_ORDER[i]],
                    index=u_wf_ix,
                )

            with st.container(border=True):
                _card_start("1 · Datos de la persona")
                uc1, uc2 = st.columns(2)
                with uc1:
                    u_fn = st.text_input("Nombre", value=cur.get("first_name") or "")
                with uc2:
                    u_ln = st.text_input("Apellido", value=cur.get("last_name") or "")
                u_addr = st.text_area("Dirección completa", value=cur.get("address_line") or "", height=88)
                dob = cur.get("date_of_birth")
                u_dob = st.date_input(
                    "Fecha de nacimiento",
                    value=date.fromisoformat(str(dob)[:10]) if dob else None,
                )

            with st.container(border=True):
                _card_start("2 · Datos de la licencia")
                u_lic = st.text_input("Número de licencia", value=cur.get("license_number") or "")
                ur1, ur2 = st.columns(2)
                with ur1:
                    u_st = st.selectbox(
                        "Estado de la licencia",
                        options=STATUS_KEYS,
                        format_func=lambda x: STATUS_LABEL[x],
                        index=st_ix,
                    )
                with ur2:
                    u_iss_st = st.text_input(
                        "Estado emisor (EE. UU.)",
                        value=cur.get("license_issuing_state") or "",
                        max_chars=4,
                    )
                isd = cur.get("license_issued_date")
                exp = cur.get("license_expiry_date")
                ud1, ud2 = st.columns(2)
                with ud1:
                    u_isd = st.date_input(
                        "Fecha de emisión",
                        value=date.fromisoformat(str(isd)[:10]) if isd else None,
                    )
                with ud2:
                    u_exp = st.date_input(
                        "Fecha de expiración",
                        value=date.fromisoformat(str(exp)[:10]) if exp else date.today(),
                    )

            with st.container(border=True):
                _card_start("3 · Plataformas")
                u_plat = {}
                u_row1 = st.columns(4)
                u_row2 = st.columns(4)
                for i, (field, lbl) in enumerate(PLATFORM_FIELDS):
                    ubox = u_row1[i] if i < 4 else u_row2[i - 4]
                    with ubox:
                        u_plat[field] = st.checkbox(lbl, value=bool(cur.get(field)), key=f"u_{e_pick}_{field}")

            with st.container(border=True):
                _card_start("4 · Fotos (reemplazo opcional)", "Si subís un archivo nuevo, reemplaza la imagen anterior.")
                uf1, uf2, uf3 = st.columns(3)
                with uf1:
                    u_f = st.file_uploader("Nuevo frente", type=["jpg", "jpeg", "png", "webp"], key="uf")
                with uf2:
                    u_b = st.file_uploader("Nuevo dorso", type=["jpg", "jpeg", "png", "webp"], key="ub")
                with uf3:
                    u_p = st.file_uploader("Nuevo rostro (tipo carnet)", type=["jpg", "jpeg", "png", "webp"], key="up")

            with st.container(border=True):
                _card_start(
                    "5 · Cuentas vinculadas (solo lectura) y notas",
                    "Para cambiar la cuenta asociada, usá **Cuentas** o **Clientes** con modalidad a nombre de tercero.",
                )
                linked = links_map.get(e_pick, [])
                if linked:
                    st.caption("Cuentas que usan esta ficha hoy:")
                    for a in linked:
                        st.write(f"· {acct_label.get(a, a)}")
                else:
                    st.caption("Sin cuenta vinculada — aparece como **disponible** en el inventario.")
                if cu_blocked or u_sem == "background_malo":
                    st.warning("**Background malo:** al guardar se eliminan los vínculos a cuentas de esta ficha.")
                u_notes = st.text_area("Notas internas", value=cur.get("notes") or "", height=100)

            save = st.form_submit_button("Guardar cambios", type="primary", use_container_width=True)
        if save:
            if not u_fn.strip() or not u_ln.strip() or not u_lic.strip():
                st.error("Nombre, apellido y número de licencia son obligatorios.")
            elif not u_req_client:
                st.error("Elegí el cliente de la solicitud.")
            else:
                extra_u = {
                    "request_client_id": u_req_client,
                    "assigned_technician_id": u_tech,
                    "data_semaphore": u_sem,
                    "workflow_status": TPI_WORKFLOW_ORDER[u_wf],
                }
                upd = _payload_from_form(
                    u_fn,
                    u_ln,
                    u_addr,
                    u_lic,
                    u_st,
                    u_iss_st,
                    u_dob,
                    u_isd,
                    u_exp,
                    u_notes,
                    u_plat,
                    extra=extra_u,
                )
                try:
                    sb.table("third_party_identities").update(upd).eq("id", e_pick).execute()
                    if u_sem == "background_malo":
                        sb.table("account_identity_links").delete().eq("identity_id", e_pick).execute()
                    if u_f:
                        ext = (u_f.name.rsplit(".", 1)[-1] if "." in u_f.name else "jpg").lower()
                        if ext == "jpeg":
                            ext = "jpg"
                        pf = f"{e_pick}/front.{ext}"
                        storage_upload(token, pf, u_f.getvalue(), u_f.type or "image/jpeg")
                        sb.table("third_party_identities").update({"photo_front_path": pf}).eq("id", e_pick).execute()
                    if u_b:
                        ext = (u_b.name.rsplit(".", 1)[-1] if "." in u_b.name else "jpg").lower()
                        if ext == "jpeg":
                            ext = "jpg"
                        pb = f"{e_pick}/back.{ext}"
                        storage_upload(token, pb, u_b.getvalue(), u_b.type or "image/jpeg")
                        sb.table("third_party_identities").update({"photo_back_path": pb}).eq("id", e_pick).execute()
                        if u_p:
                            ext = (u_p.name.rsplit(".", 1)[-1] if "." in u_p.name else "jpg").lower()
                            if ext == "jpeg":
                                ext = "jpg"
                            pp = f"{e_pick}/portrait.{ext}"
                            storage_upload(token, pp, u_p.getvalue(), u_p.type or "image/jpeg")
                            sb.table("third_party_identities").update({"portrait_photo_path": pp}).eq("id", e_pick).execute()
                    st.cache_data.clear()
                    st.success("Actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        if delete_ok:
            if st.button("Eliminar registro y fotos", type="primary"):
                try:
                    _delete_photos_if_any(cur)
                    sb.table("third_party_identities").delete().eq("id", e_pick).execute()
                    st.cache_data.clear()
                    st.success("Eliminado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        else:
            st.caption("Solo **super usuario** o **administración** pueden eliminar registros.")

elif not edit_ok:
    st.info("Tu rol puede ver datos vinculados a tus cuentas asignadas (técnico) o todo el listado (vendedor). "
            "Alta y edición: **vendedor**, **administración** o **super usuario**.")
