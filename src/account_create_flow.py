"""Creación de cuentas por modalidad (bloques separados).

Nota: aunque sea un solo formulario, cada modalidad muestra SOLO su bloque,
para evitar confusión y mensajes cruzados.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st
from io import BytesIO

from src.account_client_license import (
    back_storage_path as client_back_path,
    front_storage_path as client_front_path,
    normalize_image_ext as client_norm_ext,
    table_available as client_license_table_available,
    upsert as upsert_client_license,
)
from src.account_solo_licencia import (
    SOLO_LICENCIA_MODALITY,
    back_storage_path,
    normalize_image_ext,
    solo_table_available,
    storage_paths_for_account,
    upsert_solo_record,
)
from src.storage_api import storage_upload
from src.storage_api import storage_download
from src.tpi_account_linking import (
    TERCERO_MODALITY,
    apply_account_tercero_identity,
    identity_option_label,
    identity_selectable_for_new_account,
    validate_tercero_link,
)
from src.ui_cards import card_header
from src.constants import PAYMENT_TERMS_LABELS, PAYMENT_TERMS_ORDER


@dataclass
class AccountCreateResult:
    created: bool
    message: str | None = None


def _selectbox_modality(
    *, key_prefix: str, schema_has_service_modality: bool, client_default: str, order: list[str], labels: dict[str, str]
) -> tuple[str | None, int]:
    try:
        default_ix = order.index(client_default)
    except ValueError:
        default_ix = 0
    # Si cambió el cliente, resetea la modalidad al default del cliente (evita que quede "pegada" a la selección anterior)
    last_client = st.session_state.get(f"{key_prefix}_last_client_for_modality")
    cur_client = st.session_state.get(f"{key_prefix}_client")
    if cur_client and cur_client != last_client:
        st.session_state[f"{key_prefix}_modality_ix"] = default_ix
        st.session_state[f"{key_prefix}_last_client_for_modality"] = cur_client
    ix = st.selectbox(
        "Modalidad de servicio",
        options=list(range(len(order))),
        format_func=lambda i: labels[order[i]],
        disabled=not schema_has_service_modality,
        index=default_ix,
        key=f"{key_prefix}_modality_ix",
    )
    mod_key = order[ix] if schema_has_service_modality else None
    return mod_key, ix


def render_account_create_form(
    *,
    sb,
    token: str,
    key_prefix: str,
    schema_has_service_modality: bool,
    schema_has_solo_licencia: bool | None,
    service_modality_order: list[str],
    service_modality_labels: dict[str, str],
    service_modality_help: dict[str, str],
    clients: list[dict],
    client_id_default_modality: dict[str, str],
    plats: list[dict],
    techs: list[dict],
    tpi_rows: list[dict],
    links_by_i: dict[str, list[str]],
    status_options: list[tuple[str, str]],
    sale_options: list[tuple[str, str]],
    preset_client_id: str | None = None,
) -> AccountCreateResult:
    """Dibuja el formulario y, si se envía, crea la cuenta y sus registros ligados."""
    cid = {c["id"]: c.get("name") or "—" for c in clients}
    pid = {p["id"]: (p.get("name") or p.get("code") or "—") for p in plats}
    tid = {t["id"]: t.get("name") or "—" for t in techs}
    plat_code = {p["id"]: (p.get("code") or "") for p in plats}

    if schema_has_solo_licencia is None:
        schema_has_solo_licencia = solo_table_available(sb)
    schema_has_client_license = client_license_table_available(sb)

    if not clients or not plats:
        st.warning("Necesitás al menos un cliente y plataformas cargadas.")
        return AccountCreateResult(created=False)

    # IMPORTANTE (Streamlit): dentro de st.form los cambios NO rerenderizan el layout.
    # Por eso, los selectores que cambian qué bloque se muestra van FUERA del formulario.
    with st.container(border=True):
        card_header("1 · Cliente y plataforma", "#1565C0")
        client_opts = [c["id"] for c in clients]
        if preset_client_id and preset_client_id in client_opts:
            client_id = st.selectbox(
                "Cliente",
                options=client_opts,
                format_func=lambda x: cid.get(x, str(x)),
                index=client_opts.index(preset_client_id),
                key=f"{key_prefix}_client",
            )
        else:
            client_id = st.selectbox(
                "Cliente", options=client_opts, format_func=lambda x: cid.get(x, str(x)), key=f"{key_prefix}_client"
            )
        platform_id = st.selectbox(
            "Plataforma",
            options=[p["id"] for p in plats],
            format_func=lambda x: pid.get(x, str(x)),
            key=f"{key_prefix}_platform",
        )

    with st.container(border=True):
        card_header("2 · Modalidad (elige un formulario)", "#6A1B9A")
        client_default = client_id_default_modality.get(str(client_id)) or "cuenta_nombre_tercero"
        mod_key, ix = _selectbox_modality(
            key_prefix=key_prefix,
            schema_has_service_modality=schema_has_service_modality,
            client_default=client_default,
            order=service_modality_order,
            labels=service_modality_labels,
        )
        if schema_has_service_modality:
            st.caption(service_modality_help[service_modality_order[ix]])
        else:
            st.caption("Migración de modalidades pendiente: se usará valor compatible por defecto.")

    # Ahora sí: formulario de captura/creación (layout estable)
    with st.form(f"{key_prefix}_create_account"):
        with st.container(border=True):
            card_header("3 · Formulario según modalidad", "#455A64", "Verás solo el bloque de la modalidad elegida arriba.")

            # 2a) Tercero: solo si corresponde
            tpi_pick = None
            if schema_has_service_modality and mod_key == TERCERO_MODALITY:
                st.markdown("**Formulario A · Cuenta a nombre de tercero**")
                st.caption("Obligatorio: asignar un dato **disponible** del inventario.")
                tpi_by_id = {str(r["id"]): r for r in tpi_rows}
                ter_new_opts = [
                    r for r in tpi_rows if identity_selectable_for_new_account(r, str(r["id"]), links_by_i)
                ]
                tpi_options: list = [None] + [str(r["id"]) for r in ter_new_opts]

                def _fmt_tpi(x):
                    if x is None:
                        return "— Elegí una ficha disponible —"
                    return identity_option_label(tpi_by_id.get(str(x), {}))

                tpi_pick = st.selectbox(
                    "Dato de tercero (inventario)",
                    options=tpi_options,
                    format_func=_fmt_tpi,
                    help="Obligatorio para modalidad a nombre de tercero.",
                    key=f"{key_prefix}_tpi",
                )
                if not ter_new_opts:
                    st.caption("No hay fichas disponibles: cargalas en **Datos terceros**.")
                if tpi_pick:
                    cur = tpi_by_id.get(str(tpi_pick), {})
                    if not cur.get("portrait_photo_path"):
                        st.error("A este dato le falta **foto tipo carnet (frente)**. Cargala en **Datos terceros** para poder asignarlo.")
                    else:
                        # Preview: mostrar a quién se asigna (rostro + licencia)
                        with st.container(border=True):
                            card_header("Vista previa del dato (inventario)", "#283593", "Confirmá que es la persona correcta antes de asignar.")
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                try:
                                    st.image(
                                        BytesIO(storage_download(token, cur["portrait_photo_path"])),
                                        caption="Rostro (carnet)",
                                        use_container_width=True,
                                    )
                                except Exception:
                                    st.caption("Sin imagen de rostro.")
                            with c2:
                                p = cur.get("photo_front_path")
                                if p:
                                    try:
                                        st.image(
                                            BytesIO(storage_download(token, p)),
                                            caption="Licencia (frente)",
                                            use_container_width=True,
                                        )
                                    except Exception:
                                        st.caption("No se pudo mostrar frente.")
                                else:
                                    st.caption("Sin frente de licencia.")
                            with c3:
                                p = cur.get("photo_back_path")
                                if p:
                                    try:
                                        st.image(
                                            BytesIO(storage_download(token, p)),
                                            caption="Licencia (dorso)",
                                            use_container_width=True,
                                        )
                                    except Exception:
                                        st.caption("No se pudo mostrar dorso.")
                                else:
                                    st.caption("Sin dorso de licencia.")

            # 2b) Solo licencia: solo si corresponde
            sl_front = sl_back = None
            sl_price = 0.0
            sl_notes = ""
            if schema_has_solo_licencia and schema_has_service_modality and mod_key == SOLO_LICENCIA_MODALITY:
                st.markdown("**Formulario B · Solo licencia**")
                st.caption("Cargá los mismos datos de licencia que en terceros, pero como **licencia del cliente**.")
                if not schema_has_client_license:
                    st.warning("Falta migración **011**: `account_client_license_details`.")
                b1, b2 = st.columns(2)
                with b1:
                    cl_fn = st.text_input("Nombre *", key=f"{key_prefix}_cl_fn")
                with b2:
                    cl_ln = st.text_input("Apellido *", key=f"{key_prefix}_cl_ln")
                cl_addr = st.text_area("Dirección completa", key=f"{key_prefix}_cl_addr", height=88)
                cl_dob = st.date_input("Fecha de nacimiento (opcional)", value=None, key=f"{key_prefix}_cl_dob")
                cl_lic = st.text_input("Número de licencia *", key=f"{key_prefix}_cl_lic")
                cl_status = st.selectbox(
                    "Estado de la licencia",
                    options=["vigente", "por_vencer", "vencida", "suspendida", "revocada", "en_tramite"],
                    index=0,
                    key=f"{key_prefix}_cl_status",
                )
                cl_iss = st.text_input("Estado emisor (EE. UU.)", max_chars=4, key=f"{key_prefix}_cl_iss")
                cl_isd = st.date_input("Fecha de emisión (opcional)", value=None, key=f"{key_prefix}_cl_isd")
                cl_exp = st.date_input("Fecha de expiración *", key=f"{key_prefix}_cl_exp")
                sl_front = st.file_uploader(
                    "Foto frente de la licencia *",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"{key_prefix}_sl_front",
                )
                sl_back = st.file_uploader(
                    "Foto dorso (opcional)",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"{key_prefix}_sl_back",
                )
                sl_price = st.number_input(
                    "Precio de venta cobrado",
                    min_value=0.0,
                    value=0.0,
                    step=10.0,
                    key=f"{key_prefix}_sl_price",
                )
                sl_notes = st.text_area("Notas", key=f"{key_prefix}_sl_notes", height=72)

            # 2c) Social/SSN completo
            social_obtained = False
            ssn_full = ""
            if schema_has_service_modality and mod_key == "cliente_licencia_social_activacion_cupo":
                st.markdown("**Formulario C · Activación por cupo**")
                st.caption("Cargá licencia + Social/SSN completo (provisto por el cliente).")
                if not schema_has_client_license:
                    st.warning("Falta migración **011**: `account_client_license_details`.")
                c1, c2 = st.columns(2)
                with c1:
                    ac_fn = st.text_input("Nombre *", key=f"{key_prefix}_ac_fn")
                with c2:
                    ac_ln = st.text_input("Apellido *", key=f"{key_prefix}_ac_ln")
                ac_addr = st.text_area("Dirección completa", key=f"{key_prefix}_ac_addr", height=88)
                ac_dob = st.date_input("Fecha de nacimiento (opcional)", value=None, key=f"{key_prefix}_ac_dob")
                ac_lic = st.text_input("Número de licencia *", key=f"{key_prefix}_ac_lic")
                ac_status = st.selectbox(
                    "Estado de la licencia",
                    options=["vigente", "por_vencer", "vencida", "suspendida", "revocada", "en_tramite"],
                    index=0,
                    key=f"{key_prefix}_ac_status",
                )
                ac_iss = st.text_input("Estado emisor (EE. UU.)", max_chars=4, key=f"{key_prefix}_ac_iss")
                ac_isd = st.date_input("Fecha de emisión (opcional)", value=None, key=f"{key_prefix}_ac_isd")
                ac_exp = st.date_input("Fecha de expiración *", key=f"{key_prefix}_ac_exp")
                ac_front = st.file_uploader(
                    "Foto frente de la licencia *",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"{key_prefix}_ac_front",
                )
                ac_back = st.file_uploader(
                    "Foto dorso (opcional)",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"{key_prefix}_ac_back",
                )
                social_obtained = st.checkbox("¿Social (SSN) ya conseguido?", value=True, key=f"{key_prefix}_social")
                ssn_full = st.text_input("Social/SSN (completo) *", key=f"{key_prefix}_ssn_full")
                ac_notes = st.text_area("Notas", key=f"{key_prefix}_ac_notes", height=72)
            else:
                social_obtained = st.checkbox("¿Se consiguió Social (SSN)?", value=False, key=f"{key_prefix}_social")
                ssn_full = st.text_input("Social/SSN (completo)", key=f"{key_prefix}_ssn_full")

        # Paso 4: Operación (venta/alquiler, estado, técnico)
        with st.container(border=True):
            card_header("4 · Operación y asignación", "#EF6C00")
            sale_type = st.selectbox(
                "Tipo", options=[x[0] for x in sale_options], format_func=lambda x: dict(sale_options)[x], key=f"{key_prefix}_sale"
            )
            sale_price = 0.0
            payment_terms = None
            if sale_type == "venta":
                sale_price = st.number_input(
                    "Monto de venta",
                    min_value=0.0,
                    value=0.0,
                    step=10.0,
                    key=f"{key_prefix}_sale_price",
                )
                payment_terms = st.selectbox(
                    "Forma de pago",
                    options=PAYMENT_TERMS_ORDER,
                    format_func=lambda x: PAYMENT_TERMS_LABELS.get(x, x),
                    key=f"{key_prefix}_payment_terms",
                )
            status = st.selectbox(
                "Estado inicial",
                options=[x[0] for x in status_options],
                format_func=lambda x: dict(status_options)[x],
                key=f"{key_prefix}_status",
            )
            technician_id = st.selectbox(
                "Técnico (opcional)",
                options=[None] + [t["id"] for t in techs],
                format_func=lambda x: "—" if x is None else tid.get(x, str(x)),
                key=f"{key_prefix}_tech",
            )
            quality_ok = st.checkbox("Cuenta OK (lista para entregar)", value=False, key=f"{key_prefix}_qok")

        with st.container(border=True):
            card_header("5 · Notas", "#546E7A")
            ext = st.text_input("Referencia externa", key=f"{key_prefix}_ext")
            req_notes = st.text_area("Notas de requisitos", key=f"{key_prefix}_req")
            rw = 0.0
            if sale_type == "alquiler":
                rw = st.number_input(
                    "Monto alquiler semanal",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key=f"{key_prefix}_rw",
                )

        submitted = st.form_submit_button("Crear cuenta", type="primary", use_container_width=True)

    if not submitted:
        return AccountCreateResult(created=False)

    # Validaciones (claras y por modalidad)
    if schema_has_service_modality and mod_key == TERCERO_MODALITY and not tpi_pick:
        st.error("Modalidad a nombre de tercero: elegí una ficha **disponible** del inventario.")
        return AccountCreateResult(created=False)
    if schema_has_service_modality and mod_key == TERCERO_MODALITY and tpi_pick:
        tpi_by_id = {str(r["id"]): r for r in tpi_rows}
        cur = tpi_by_id.get(str(tpi_pick), {})
        if not cur.get("portrait_photo_path"):
            st.error("Formulario A: el dato seleccionado no tiene **foto tipo carnet (frente)**.")
            return AccountCreateResult(created=False)
    if schema_has_service_modality and mod_key == "cliente_licencia_social_activacion_cupo" and not (ssn_full or "").strip():
        st.error("Modalidad activación por cupo: ingresá el **Social/SSN completo**.")
        return AccountCreateResult(created=False)
    if schema_has_solo_licencia and schema_has_service_modality and mod_key == SOLO_LICENCIA_MODALITY:
        if not sl_front:
            st.error("Formulario B: subí la **foto del frente**.")
            return AccountCreateResult(created=False)
        if not (st.session_state.get(f"{key_prefix}_cl_fn") or "").strip() or not (st.session_state.get(f"{key_prefix}_cl_ln") or "").strip():
            st.error("Formulario B: nombre y apellido son obligatorios.")
            return AccountCreateResult(created=False)
        if not (st.session_state.get(f"{key_prefix}_cl_lic") or "").strip():
            st.error("Formulario B: número de licencia es obligatorio.")
            return AccountCreateResult(created=False)
        if sale_type == "venta" and (not sl_price or sl_price <= 0):
            st.error("Formulario B: en venta, indicá el **precio cobrado** (> 0).")
            return AccountCreateResult(created=False)

    if schema_has_service_modality and mod_key == "cliente_licencia_social_activacion_cupo":
        if not (ssn_full or "").strip():
            st.error("Formulario C: Social/SSN **completo** es obligatorio.")
            return AccountCreateResult(created=False)
        if not (st.session_state.get(f"{key_prefix}_ac_fn") or "").strip() or not (st.session_state.get(f"{key_prefix}_ac_ln") or "").strip():
            st.error("Formulario C: nombre y apellido son obligatorios.")
            return AccountCreateResult(created=False)
        if not (st.session_state.get(f"{key_prefix}_ac_lic") or "").strip():
            st.error("Formulario C: número de licencia es obligatorio.")
            return AccountCreateResult(created=False)
        if not st.session_state.get(f"{key_prefix}_ac_front"):
            st.error("Formulario C: subí la **foto del frente**.")
            return AccountCreateResult(created=False)

    if sale_type == "venta":
        if not sale_price or sale_price <= 0:
            st.error("En **Venta**, el **monto de venta** es obligatorio (> 0).")
            return AccountCreateResult(created=False)
        if payment_terms not in PAYMENT_TERMS_ORDER:
            st.error("En **Venta**, elegí forma de pago (contado o crédito).")
            return AccountCreateResult(created=False)

    # Insert cuenta + vínculos
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "client_id": client_id,
        "platform_id": platform_id,
        "sale_type": sale_type,
        "status": status,
        "technician_id": technician_id,
        "external_ref": ext or None,
        "requirements_notes": req_notes or None,
        "social_obtained": bool(social_obtained),
        "ssn_full": (ssn_full or "").strip() or None,
        "quality_ok": bool(quality_ok),
    }
    if sale_type == "venta":
        payload["sale_price"] = float(sale_price)
        payload["payment_terms"] = payment_terms
    if schema_has_service_modality:
        payload["service_modality"] = mod_key
    if technician_id:
        payload["assigned_at"] = now
    if sale_type == "alquiler" and rw and rw > 0:
        payload["rental_weekly_amount"] = float(rw)

    try:
        ins = sb.table("accounts").insert(payload).execute()
        new_aid = str(ins.data[0]["id"])

        if schema_has_service_modality:
            link_id = tpi_pick if mod_key == TERCERO_MODALITY else None
            if mod_key == TERCERO_MODALITY and link_id:
                verr = validate_tercero_link(sb, new_aid, str(link_id))
                if verr:
                    sb.table("accounts").delete().eq("id", new_aid).execute()
                    st.error(verr)
                    return AccountCreateResult(created=False)
                apply_account_tercero_identity(sb, new_aid, mod_key, str(link_id))
            else:
                apply_account_tercero_identity(sb, new_aid, mod_key or "cuenta_nombre_tercero", None)

        if schema_has_solo_licencia and schema_has_service_modality and mod_key == SOLO_LICENCIA_MODALITY:
            ext_f = normalize_image_ext(sl_front.name)
            fp, _ = storage_paths_for_account(new_aid, ext_f, None)
            storage_upload(token, fp, sl_front.getvalue(), sl_front.type or "image/jpeg")
            back_path = None
            if sl_back:
                ext_b = normalize_image_ext(sl_back.name)
                back_path = back_storage_path(new_aid, ext_b)
                storage_upload(token, back_path, sl_back.getvalue(), sl_back.type or "image/jpeg")
            upsert_solo_record(sb, new_aid, float(sl_price), sl_notes or None, fp, back_path)

        # Guardar licencia del cliente (solo licencia / activación) en tabla separada (si existe)
        if schema_has_client_license and schema_has_service_modality and mod_key in (
            SOLO_LICENCIA_MODALITY,
            "cliente_licencia_social_activacion_cupo",
        ):
            if mod_key == SOLO_LICENCIA_MODALITY:
                front_file = sl_front
                back_file = sl_back
                form = {
                    "first_name": (st.session_state.get(f"{key_prefix}_cl_fn") or "").strip(),
                    "last_name": (st.session_state.get(f"{key_prefix}_cl_ln") or "").strip(),
                    "address_line": (st.session_state.get(f"{key_prefix}_cl_addr") or "").strip() or None,
                    "license_number": (st.session_state.get(f"{key_prefix}_cl_lic") or "").strip(),
                    "license_status": st.session_state.get(f"{key_prefix}_cl_status") or "vigente",
                    "license_issuing_state": (st.session_state.get(f"{key_prefix}_cl_iss") or "").strip() or None,
                    "date_of_birth": st.session_state.get(f"{key_prefix}_cl_dob").isoformat()
                    if st.session_state.get(f"{key_prefix}_cl_dob")
                    else None,
                    "license_issued_date": st.session_state.get(f"{key_prefix}_cl_isd").isoformat()
                    if st.session_state.get(f"{key_prefix}_cl_isd")
                    else None,
                    "license_expiry_date": st.session_state.get(f"{key_prefix}_cl_exp").isoformat()
                    if st.session_state.get(f"{key_prefix}_cl_exp")
                    else None,
                    "notes": (sl_notes or "").strip() or None,
                }
            else:
                front_file = st.session_state.get(f"{key_prefix}_ac_front")
                back_file = st.session_state.get(f"{key_prefix}_ac_back")
                form = {
                    "first_name": (st.session_state.get(f"{key_prefix}_ac_fn") or "").strip(),
                    "last_name": (st.session_state.get(f"{key_prefix}_ac_ln") or "").strip(),
                    "address_line": (st.session_state.get(f"{key_prefix}_ac_addr") or "").strip() or None,
                    "license_number": (st.session_state.get(f"{key_prefix}_ac_lic") or "").strip(),
                    "license_status": st.session_state.get(f"{key_prefix}_ac_status") or "vigente",
                    "license_issuing_state": (st.session_state.get(f"{key_prefix}_ac_iss") or "").strip() or None,
                    "date_of_birth": st.session_state.get(f"{key_prefix}_ac_dob").isoformat()
                    if st.session_state.get(f"{key_prefix}_ac_dob")
                    else None,
                    "license_issued_date": st.session_state.get(f"{key_prefix}_ac_isd").isoformat()
                    if st.session_state.get(f"{key_prefix}_ac_isd")
                    else None,
                    "license_expiry_date": st.session_state.get(f"{key_prefix}_ac_exp").isoformat()
                    if st.session_state.get(f"{key_prefix}_ac_exp")
                    else None,
                    "notes": (st.session_state.get(f"{key_prefix}_ac_notes") or "").strip() or None,
                }

            ext_cf = client_norm_ext(front_file.name)
            c_front = client_front_path(new_aid, ext_cf)
            storage_upload(token, c_front, front_file.getvalue(), front_file.type or "image/jpeg")
            c_back = None
            if back_file:
                ext_cb = client_norm_ext(back_file.name)
                c_back = client_back_path(new_aid, ext_cb)
                storage_upload(token, c_back, back_file.getvalue(), back_file.type or "image/jpeg")

            upsert_client_license(
                sb,
                {
                    "account_id": new_aid,
                    **form,
                    "photo_front_path": c_front,
                    "photo_back_path": c_back,
                },
            )

        return AccountCreateResult(created=True, message="Cuenta creada.")
    except Exception as e:
        st.error(f"No se pudo crear: {e}")
        return AccountCreateResult(created=False)

