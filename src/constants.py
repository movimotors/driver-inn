"""Etiquetas y colores del semáforo de estado de cuenta."""

ACCOUNT_STATUS_ORDER = [
    "solicitud",
    "asignada",
    "en_proceso",
    "requisitos_ok",
    "entregada",
    "suspendida",
    "cancelada",
]

ACCOUNT_STATUS_LABELS = {
    "solicitud": "Solicitud",
    "asignada": "Asignada",
    "en_proceso": "En proceso",
    "requisitos_ok": "Requisitos OK",
    "entregada": "Entregada",
    "suspendida": "Suspendida",
    "cancelada": "Cancelada",
}

# Color sugerido para badges (hex)
ACCOUNT_STATUS_COLOR = {
    "solicitud": "#9E9E9E",
    "asignada": "#FBC02D",
    "en_proceso": "#FB8C00",
    "requisitos_ok": "#43A047",
    "entregada": "#1E88E5",
    "suspendida": "#E53935",
    "cancelada": "#757575",
}

SALE_TYPE_LABELS = {"venta": "Venta", "alquiler": "Alquiler"}

# Modalidad de servicio (negocio): qué tipo de creación/gestión es la cuenta
SERVICE_MODALITY_ORDER = [
    "cuenta_nombre_tercero",
    "cliente_licencia_sin_social",
    "cliente_licencia_social_activacion_cupo",
]

SERVICE_MODALITY_LABELS = {
    "cuenta_nombre_tercero": "Cuenta a nombre de tercero",
    "cliente_licencia_sin_social": "Cliente con licencia — sin social (SSN)",
    "cliente_licencia_social_activacion_cupo": "Cliente con licencia y SSN — activación por cupo",
}

SERVICE_MODALITY_HELP = {
    "cuenta_nombre_tercero": (
        "Se crea la cuenta usando **datos de un tercero** (licencia registrada en Datos terceros). "
        "Vinculá esa ficha a esta cuenta en el módulo correspondiente."
    ),
    "cliente_licencia_sin_social": (
        "El **cliente ya tiene licencia** pero **aún no tiene** número de seguro social (SSN) u otros datos sociales. "
        "El flujo es distinto al de cuenta a nombre de tercero."
    ),
    "cliente_licencia_social_activacion_cupo": (
        "El cliente **tiene licencia y SSN**; el trabajo es **activar** la cuenta cuando haya **cupo** en la plataforma."
    ),
}
