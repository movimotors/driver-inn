"""Formulario unificado de creación de cuentas (Cuentas / Clientes).

Objetivo: evitar duplicación de lógica y mostrar solo lo relevante según modalidad.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st

from src.account_solo_licencia import (
    SOLO_LICENCIA_MODALITY,
    back_storage_path,
    normalize_image_ext,
    solo_table_available,
    storage_paths_for_account,
    upsert_solo_record,
)
from src.storage_api import storage_upload
from src.tpi_account_linking import (
    TERCERO_MODALITY,
    apply_account_tercero_identity,
    identity_option_label,
    identity_selectable_for_new_account,
    validate_tercero_link,
)
from src.ui_cards import card_header


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

    if schema_has_solo_licencia is None:
        schema_has_solo_licencia = solo_table_available(sb)

    if not clients or not plats:
        st.warning("Necesitás al menos un cliente y plataformas cargadas.")
        return AccountCreateResult(created=False)

    with st.form(f"{key_prefix}_create_account"):
        # Paso 1: Cliente + plataforma
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

        # Paso 2: Modalidad (se muestra help) + campos dinámicos
        with st.container(border=True):
            card_header("2 · Modalidad y datos necesarios", "#6A1B9A")
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

            # 2a) Tercero: solo si corresponde
            tpi_pick = None
            if schema_has_service_modality and mod_key == TERCERO_MODALITY:
                st.markdown("**Cuenta a nombre de tercero** · Elegí una ficha disponible del inventario.")
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

            # 2b) Solo licencia: solo si corresponde
            sl_front = sl_back = None
            sl_price = 0.0
            sl_notes = ""
            if schema_has_solo_licencia and schema_has_service_modality and mod_key == SOLO_LICENCIA_MODALITY:
                st.markdown("**Solo licencia** · Subí foto(s) y registra el precio de venta.")
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

            # 2c) Activación: SSN requerido
            social_obtained = False
            ssn_last4 = ""
            if schema_has_service_modality and mod_key == "cliente_licencia_social_activacion_cupo":
                st.markdown("**Activación por cupo** · Aquí el SSN es parte del requisito.")
                social_obtained = st.checkbox("¿Social (SSN) ya conseguido?", value=True, key=f"{key_prefix}_social")
                ssn_last4 = st.text_input("SSN (últimos 4) *", max_chars=4, key=f"{key_prefix}_ssn4")
            else:
                social_obtained = st.checkbox("¿Se consiguió Social (SSN)?", value=False, key=f"{key_prefix}_social")
                ssn_last4 = st.text_input("SSN (últimos 4)", max_chars=4, key=f"{key_prefix}_ssn4")

        # Paso 3: Operación (venta/alquiler, estado, técnico)
        with st.container(border=True):
            card_header("3 · Operación y asignación", "#EF6C00")
            sale_type = st.selectbox(
                "Tipo", options=[x[0] for x in sale_options], format_func=lambda x: dict(sale_options)[x], key=f"{key_prefix}_sale"
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
            card_header("4 · Notas", "#546E7A")
            ext = st.text_input("Referencia externa", key=f"{key_prefix}_ext")
            req_notes = st.text_area("Notas de requisitos", key=f"{key_prefix}_req")
            rw = st.number_input(
                "Monto alquiler semanal (solo si aplica)", min_value=0.0, value=0.0, step=1.0, key=f"{key_prefix}_rw"
            )

        submitted = st.form_submit_button("Crear cuenta", type="primary", use_container_width=True)

    if not submitted:
        return AccountCreateResult(created=False)

    # Validaciones (claras y por modalidad)
    if schema_has_service_modality and mod_key == TERCERO_MODALITY and not tpi_pick:
        st.error("Modalidad a nombre de tercero: elegí una ficha **disponible** del inventario.")
        return AccountCreateResult(created=False)
    if schema_has_service_modality and mod_key == "cliente_licencia_social_activacion_cupo" and not (ssn_last4 or "").strip():
        st.error("Modalidad activación por cupo: ingresá el **SSN (últimos 4)**.")
        return AccountCreateResult(created=False)
    if schema_has_solo_licencia and schema_has_service_modality and mod_key == SOLO_LICENCIA_MODALITY:
        if not sl_front:
            st.error("Modalidad solo licencia: subí la **foto del frente**.")
            return AccountCreateResult(created=False)
        if sale_type == "venta" and (not sl_price or sl_price <= 0):
            st.error("Modalidad solo licencia en venta: ingresá el **precio cobrado** (> 0).")
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
        "ssn_last4": (ssn_last4 or "").strip() or None,
        "quality_ok": bool(quality_ok),
    }
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

        return AccountCreateResult(created=True, message="Cuenta creada.")
    except Exception as e:
        st.error(f"No se pudo crear: {e}")
        return AccountCreateResult(created=False)

