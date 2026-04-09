import sys
from io import BytesIO
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from src.config import supabase_configured
from src.constants import (
    ACCOUNT_STATUS_COLOR,
    ACCOUNT_STATUS_LABELS,
    ACCOUNT_STATUS_ORDER,
    ACCOUNT_PHONE_SOURCE_LABELS,
    ACCOUNT_PHONE_SOURCE_ORDER,
    SALE_TYPE_LABELS,
    SERVICE_MODALITY_HELP,
    SERVICE_MODALITY_LABELS,
    SERVICE_MODALITY_ORDER,
)
from src.account_solo_licencia import (
    SOLO_LICENCIA_MODALITY,
    delete_record,
    fetch_solo_map,
    front_storage_path,
    normalize_image_ext,
    remove_storage_files,
    solo_table_available,
)
from src.db import fetch_accounts_list_with_modality_fallback, get_client
from src.rbac import ROLE_TECNICO, require_login
from src.storage_api import storage_download, storage_upload
from src.tpi_account_linking import (
    TERCERO_MODALITY,
    apply_account_tercero_identity,
    current_tercero_identity_id,
    identity_option_label,
    identity_rows_for_account_editor,
    load_identities_and_links,
    validate_tercero_link,
)
from src.account_create_flow import render_account_create_form
from src.ui_cards import card_header

st.title("Cuentas delivery — semáforo de estado")

with st.expander("Modalidades de servicio (cómo se trabaja cada cuenta)", expanded=False):
    st.markdown(
        "Ofrecés **tres tipos** de creación/gestión; elegí la correcta al crear o editar la cuenta para que el equipo sepa qué falta."
    )
    for key in SERVICE_MODALITY_ORDER:
        st.markdown(f"**{SERVICE_MODALITY_LABELS[key]}** — {SERVICE_MODALITY_HELP[key]}")

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
    try:
        clients = (c.table("clients").select("id,name,default_service_modality").order("name").execute().data) or []
    except Exception:
        clients = (c.table("clients").select("id,name").order("name").execute().data) or []
        for row in clients:
            row["default_service_modality"] = "cuenta_nombre_tercero"
    techs = (c.table("technicians").select("id,name,active").eq("active", True).order("name").execute().data) or []
    plats = (c.table("delivery_platforms").select("id,name,code").eq("active", True).order("name").execute().data) or []
    return clients, techs, plats


@st.cache_data(ttl=30)
def load_accounts_full(_token: str):
    c = get_client(_token)
    return fetch_accounts_list_with_modality_fallback(c)


def status_badge(status: str) -> str:
    label = ACCOUNT_STATUS_LABELS.get(status, status)
    color = ACCOUNT_STATUS_COLOR.get(status, "#757575")
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{label}</span>'


if st.button("Refrescar"):
    st.cache_data.clear()
    st.rerun()

try:
    clients, techs, plats = load_lookups(token)
    accounts, schema_has_service_modality = load_accounts_full(token)
except Exception as e:
    st.error(f"Error al cargar datos: {e}")
    st.stop()

tpi_rows: list = []
links_by_i: dict = {}
try:
    tpi_rows, links_by_i, _ = load_identities_and_links(sb)
except Exception:
    pass
tpi_by_id = {str(r["id"]): r for r in tpi_rows}

schema_has_solo_licencia = solo_table_available(sb)
solo_map: dict = fetch_solo_map(sb) if schema_has_solo_licencia else {}

if not schema_has_service_modality:
    st.warning(
        "La base **aún no tiene** la columna **service_modality** (modalidades de servicio). "
        "Ejecutá en Supabase SQL Editor: **`supabase/migration_006_account_service_modality.sql`**. "
        "Hasta entonces la app funciona en modo compatible, pero **no se guardará** la modalidad al crear/editar."
    )

if schema_has_service_modality and not schema_has_solo_licencia:
    st.warning(
        "Para **fotos y precio** en modalidad **solo licencia**, ejecutá en Supabase: "
        "**`supabase/migration_008_account_solo_licencia.sql`**."
    )

cid = {c["id"]: c["name"] for c in clients}
client_default_mod = {str(c["id"]): c.get("default_service_modality") for c in clients if c.get("id")}
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
    mod = row.get("service_modality") or "cuenta_nombre_tercero"
    mod_lbl = SERVICE_MODALITY_LABELS.get(mod, mod)
    aid = str(row["id"])
    sl_extra = ""
    if (
        schema_has_solo_licencia
        and mod == SOLO_LICENCIA_MODALITY
        and (solo_map.get(aid) or {}).get("photo_front_path")
    ):
        sl = solo_map[aid]
        sl_extra = f" · **Solo licencia** · ${float(sl.get('sale_price', 0)):,.2f} · 📷 registro"
    elif schema_has_solo_licencia and mod == SOLO_LICENCIA_MODALITY:
        sl_extra = " · **Solo licencia** (sin registro / falta migración o datos)"
    st.markdown(
        f"**{plat}** · Cliente: {cli} · Técnico: {tech} · "
        f"{SALE_TYPE_LABELS.get(row['sale_type'], row['sale_type'])} · *{mod_lbl}*{sl_extra} — {badge}",
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
        with st.container(border=True):
            card_header(
                "Crear cuenta (paso a paso)",
                "#1E88E5",
                "El formulario muestra solo lo necesario según la **modalidad** del cliente/cuenta.",
            )
        res = render_account_create_form(
            sb=sb,
            token=token,
            key_prefix="cuentas",
            schema_has_service_modality=schema_has_service_modality,
            schema_has_solo_licencia=schema_has_solo_licencia,
            service_modality_order=SERVICE_MODALITY_ORDER,
            service_modality_labels=SERVICE_MODALITY_LABELS,
            service_modality_help=SERVICE_MODALITY_HELP,
            clients=clients,
            client_id_default_modality=client_default_mod,
            plats=plats,
            techs=techs,
            tpi_rows=tpi_rows,
            links_by_i=links_by_i,
            status_options=STATUS_OPTIONS,
            sale_options=SALE_OPTIONS,
        )
        if res.created:
            st.cache_data.clear()
            st.success(res.message or "Cuenta creada.")
            st.rerun()
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
    existing_sl = solo_map.get(acc) if schema_has_solo_licencia else None
    if existing_sl and existing_sl.get("photo_front_path"):
        with st.expander("Registro solo licencia · fotos actuales", expanded=False):
            st.markdown(f"**Precio de venta registrado:** ${float(existing_sl.get('sale_price') or 0):,.2f}")
            if existing_sl.get("notes"):
                st.caption(existing_sl["notes"])
            c1, c2 = st.columns(2)
            with c1:
                try:
                    st.image(
                        BytesIO(storage_download(token, existing_sl["photo_front_path"])),
                        caption="Frente",
                        use_container_width=True,
                    )
                except Exception:
                    st.caption("No se pudo mostrar el frente.")
            with c2:
                pb = existing_sl.get("photo_back_path")
                if pb:
                    try:
                        st.image(BytesIO(storage_download(token, pb)), caption="Dorso", use_container_width=True)
                    except Exception:
                        st.caption("No se pudo mostrar el dorso.")
                else:
                    st.caption("Sin foto de dorso.")
    tech_options: list = [None] + [t["id"] for t in techs]
    try:
        tech_index = tech_options.index(current.get("technician_id"))
    except ValueError:
        tech_index = 0
    try:
        st_index = ACCOUNT_STATUS_ORDER.index(current["status"])
    except ValueError:
        st_index = 0
    cur_mod = current.get("service_modality") or "cuenta_nombre_tercero"
    try:
        mod_index = SERVICE_MODALITY_ORDER.index(cur_mod)
    except ValueError:
        mod_index = 0

    cur_tid = current_tercero_identity_id(sb, acc) if tpi_rows else None
    ter_edit_rows = identity_rows_for_account_editor(tpi_rows, links_by_i, acc, cur_tid)
    ter_edit_ids: list = [None] + [str(r["id"]) for r in ter_edit_rows]
    try:
        tpi_ix = ter_edit_ids.index(cur_tid) if cur_tid and cur_tid in ter_edit_ids else 0
    except ValueError:
        tpi_ix = 0
    safe_tpi_ix = min(tpi_ix, max(0, len(ter_edit_ids) - 1))
    upd_tpi_key = f"ua_tpi_{acc}"

    with st.form("upd_account"):
        new_modality_ix = st.selectbox(
            "Modalidad de servicio",
            options=list(range(len(SERVICE_MODALITY_ORDER))),
            format_func=lambda i: SERVICE_MODALITY_LABELS[SERVICE_MODALITY_ORDER[i]],
            index=mod_index,
            help="Corregí la modalidad si la cuenta se mal clasificó al crearla.",
            disabled=not schema_has_service_modality,
        )
        if schema_has_service_modality:
            st.caption(SERVICE_MODALITY_HELP[SERVICE_MODALITY_ORDER[new_modality_ix]])
        else:
            st.caption("Migración 006 pendiente: la modalidad no se persiste.")
        if schema_has_service_modality:

            def _fmt_ua_tpi(x):
                if x is None:
                    return "— Sin vínculo —"
                return identity_option_label(tpi_by_id.get(str(x), {}))

            st.selectbox(
                "Dato de tercero (inventario)",
                options=ter_edit_ids,
                index=safe_tpi_ix,
                format_func=_fmt_ua_tpi,
                help="Ficha vinculada a esta cuenta. Solo **disponibles** + la actual. Cambiá modalidad para quitar el vínculo.",
                key=upd_tpi_key,
            )
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
        with st.container(border=True):
            card_header("Social (SSN) y calidad", "#00897B")
            ua_social = st.checkbox(
                "¿Se consiguió Social (SSN) para esta cuenta?",
                value=bool(current.get("social_obtained") or False),
                key=f"ua_social_{acc}",
            )
            ua_ssn4 = st.text_input(
                "SSN (últimos 4)",
                value=(current.get("ssn_last4") or ""),
                max_chars=4,
                key=f"ua_ssn4_{acc}",
            )
            ua_quality_ok = st.checkbox(
                "Cuenta OK (lista para entregar)",
                value=bool(current.get("quality_ok") or False),
                key=f"ua_qok_{acc}",
            )
            if ua_quality_ok:
                st.caption("Sugerencia: dejar el estado en **Requisitos OK** o **Entregada** cuando aplique.")
        show_sl = schema_has_solo_licencia and (
            cur_mod == SOLO_LICENCIA_MODALITY
            or SERVICE_MODALITY_ORDER[new_modality_ix] == SOLO_LICENCIA_MODALITY
        )
        ua_sl_price = float((existing_sl or {}).get("sale_price") or 0)
        ua_sl_notes = (existing_sl or {}).get("notes") or ""
        ua_sl_f = None
        ua_sl_b = None
        if show_sl:
            with st.container(border=True):
                card_header("Registro solo licencia", "#6A1B9A")
                ua_sl_price = st.number_input(
                    "Precio de venta cobrado",
                    min_value=0.0,
                    value=ua_sl_price,
                    step=10.0,
                    key=f"ua_slp_{acc}",
                    help="Si la cuenta es tipo **Venta**, debe ser mayor a 0.",
                )
                ua_sl_notes = st.text_area(
                    "Notas del registro",
                    value=ua_sl_notes,
                    key=f"ua_sln_{acc}",
                    height=72,
                )
                ua_sl_f = st.file_uploader(
                    "Reemplazar foto frente (opcional si ya hay una arriba)",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"ua_slf_{acc}",
                )
                ua_sl_b = st.file_uploader(
                    "Reemplazar o agregar dorso",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"ua_slb_{acc}",
                )
        save = st.form_submit_button("Guardar cambios")
    if save:
        old_st = current["status"]
        new_mod = (
            SERVICE_MODALITY_ORDER[new_modality_ix]
            if schema_has_service_modality
            else (current.get("service_modality") or "cuenta_nombre_tercero")
        )
        upd_tpi = st.session_state.get(upd_tpi_key) if schema_has_service_modality else None
        link_id = str(upd_tpi) if schema_has_service_modality and new_mod == TERCERO_MODALITY and upd_tpi else None
        block = False
        if schema_has_service_modality and new_mod == TERCERO_MODALITY and not upd_tpi:
            st.error(
                "Con modalidad **Cuenta a nombre de tercero** elegí una ficha del inventario o cargá una nueva en **Datos terceros**."
            )
            block = True
        elif link_id:
            verr = validate_tercero_link(sb, acc, link_id)
            if verr:
                st.error(verr)
                block = True
        if schema_has_solo_licencia and new_mod == SOLO_LICENCIA_MODALITY:
            if not ua_sl_f and not (existing_sl or {}).get("photo_front_path"):
                st.error("Modalidad **solo licencia**: subí la **foto del frente** o conservá la ya registrada.")
                block = True
            elif current["sale_type"] == "venta" and ua_sl_price <= 0:
                st.error("Con tipo **Venta** indicá el **precio cobrado** (> 0) en el registro solo licencia.")
                block = True
        if not block:
            upd = {"status": new_status, "technician_id": new_tech}
            if schema_has_service_modality:
                upd["service_modality"] = new_mod
            upd["social_obtained"] = bool(st.session_state.get(f"ua_social_{acc}"))
            upd["ssn_last4"] = (st.session_state.get(f"ua_ssn4_{acc}") or "").strip() or None
            upd["quality_ok"] = bool(st.session_state.get(f"ua_qok_{acc}"))
            from datetime import timezone

            if new_tech and not current.get("technician_id"):
                upd["assigned_at"] = datetime.now(timezone.utc).isoformat()
            if set_delivered and delivered:
                upd["delivered_at"] = delivered.isoformat()
            if set_rental_due and rental_due:
                upd["rental_next_due_date"] = rental_due.isoformat()
            try:
                sb.table("accounts").update(upd).eq("id", acc).execute()
                if schema_has_service_modality:
                    apply_account_tercero_identity(sb, acc, new_mod, link_id)
                if schema_has_solo_licencia:
                    if new_mod != SOLO_LICENCIA_MODALITY:
                        if acc in solo_map:
                            remove_storage_files(token, solo_map[acc])
                            delete_record(sb, acc)
                    else:
                        fp = (existing_sl or {}).get("photo_front_path")
                        bp = (existing_sl or {}).get("photo_back_path")
                        if ua_sl_f:
                            ext = normalize_image_ext(ua_sl_f.name)
                            fp = front_storage_path(acc, ext)
                            storage_upload(
                                token,
                                fp,
                                ua_sl_f.getvalue(),
                                ua_sl_f.type or "image/jpeg",
                            )
                        if ua_sl_b:
                            ext_b = normalize_image_ext(ua_sl_b.name)
                            bp = back_storage_path(acc, ext_b)
                            storage_upload(
                                token,
                                bp,
                                ua_sl_b.getvalue(),
                                ua_sl_b.type or "image/jpeg",
                            )
                        upsert_solo_record(
                            sb,
                            acc,
                            float(ua_sl_price),
                            ua_sl_notes or None,
                            fp,
                            bp,
                        )
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

    # --- Ejecución técnica y credenciales ---
    with st.expander("🧰 Ejecución técnica (teléfono, correo, claves)", expanded=False):
        st.info(
            "Registro interno de **cómo se creó** la cuenta: teléfono usado, correo creado y (si querés) claves. "
            "Se guarda en **texto plano** y se protege por **RLS** (solo roles/usuarios autorizados)."
        )
        if st.button("Refrescar ejecución", key=f"ref_exec_{acc}"):
            st.cache_data.clear()
            st.rerun()
        # Carga on-demand (sin cache; datos sensibles)
        try:
            aed = (sb.table("account_execution_details").select("*").eq("account_id", acc).execute().data or [])
            aed = aed[0] if aed else {}
        except Exception:
            aed = {}
        try:
            cred = (sb.table("account_credentials").select("*").eq("account_id", acc).execute().data or [])
            cred = cred[0] if cred else {}
        except Exception:
            cred = {}

        with st.form(f"exec_{acc}"):
            with st.container(border=True):
                card_header("Teléfono y correo", "#5E35B1")
            ph = st.text_input("Teléfono usado", value=aed.get("phone_number") or "")
            ps = st.selectbox(
                "Origen del teléfono",
                options=ACCOUNT_PHONE_SOURCE_ORDER,
                format_func=lambda x: ACCOUNT_PHONE_SOURCE_LABELS.get(x, x),
                index=ACCOUNT_PHONE_SOURCE_ORDER.index(aed.get("phone_source"))
                if aed.get("phone_source") in ACCOUNT_PHONE_SOURCE_ORDER
                else 0,
            )
            em = st.text_input("Correo creado para la cuenta", value=aed.get("email_created") or "")
            st.divider()
            with st.container(border=True):
                card_header("Claves (texto plano)", "#BF360C")
            email_login = st.text_input("Login del correo (si es distinto)", value=cred.get("email_login") or "")
            email_pass = st.text_input("Clave del correo", value=cred.get("email_password") or "", type="password")
            app_pass = st.text_input("Clave de la app/plataforma", value=cred.get("app_password") or "", type="password")
            save_exec = st.form_submit_button("Guardar ejecución")
        if save_exec:
            try:
                # upsert execution
                ex = sb.table("account_execution_details").select("account_id").eq("account_id", acc).execute().data or []
                payload = {
                    "account_id": acc,
                    "phone_number": ph.strip() or None,
                    "phone_source": ps or None,
                    "email_created": em.strip() or None,
                }
                if ex:
                    sb.table("account_execution_details").update(payload).eq("account_id", acc).execute()
                else:
                    sb.table("account_execution_details").insert(payload).execute()

                # upsert credentials
                ex2 = sb.table("account_credentials").select("account_id").eq("account_id", acc).execute().data or []
                payload2 = {
                    "account_id": acc,
                    "email_login": email_login.strip() or None,
                    "email_password": email_pass or None,
                    "app_password": app_pass or None,
                }
                if ex2:
                    sb.table("account_credentials").update(payload2).eq("account_id", acc).execute()
                else:
                    sb.table("account_credentials").insert(payload2).execute()
                st.success("Ejecución guardada.")
            except Exception as e:
                st.error(f"No se pudo guardar: {e}")
