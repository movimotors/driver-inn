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
