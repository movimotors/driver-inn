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
        "Se crea la cuenta usando **datos de un tercero** (ficha en **Datos terceros**). "
        "Elegí la ficha **disponible** al crear o editar la cuenta en **Cuentas** (o **Clientes → Nueva cuenta delivery**). "
        "**Datos terceros** es el inventario; la asignación a la cuenta se hace desde ahí."
    ),
    "cliente_licencia_sin_social": (
        "El **cliente ya tiene licencia** pero **aún no tiene** número de seguro social (SSN) u otros datos sociales. "
        "El flujo es distinto al de cuenta a nombre de tercero."
    ),
    "cliente_licencia_social_activacion_cupo": (
        "El cliente **tiene licencia y SSN**; el trabajo es **activar** la cuenta cuando haya **cupo** en la plataforma."
    ),
}

# --- Datos terceros: semáforo de calidad del dato ---
TPI_DATA_SEMAPHORE_ORDER = ["apto", "revisar", "background_malo"]

TPI_DATA_SEMAPHORE_LABELS = {
    "apto": "Apto — dato utilizable",
    "revisar": "En revisión",
    "background_malo": "Background malo (inutilizable)",
}

TPI_DATA_SEMAPHORE_HELP = {
    "apto": "El dato puede vincularse a cuentas delivery.",
    "revisar": "Aún no está validado para uso operativo.",
    "background_malo": "**Cuidado:** el dato queda **bloqueado**: no se asigna a más cuentas ni clientes. Aparece en alertas y listado de dato malo.",
}

TPI_DATA_SEMAPHORE_COLOR = {
    "apto": "#2E7D32",
    "revisar": "#F9A825",
    "background_malo": "#C62828",
}

# --- Kanban (flujo técnico) ---
TPI_WORKFLOW_ORDER = [
    "solicitud",
    "asignada",
    "en_proceso",
    "en_revision",
    "listo_cuentas",
    "cerrado",
]

TPI_WORKFLOW_LABELS = {
    "solicitud": "Solicitud",
    "asignada": "Asignada al técnico",
    "en_proceso": "En proceso",
    "en_revision": "En revisión",
    "listo_cuentas": "Listo para cuentas",
    "cerrado": "Cerrado",
}

# Columnas del tablero (la primera es virtual: data_semaphore = background_malo)
# Inventario (resumen operativo)
TPI_INVENTORY_BUCKET_LABELS = {
    "disponible": "Disponible — sin cuenta asignada",
    "asignado": "Asignado — ya vinculado a cuenta(s)",
    "malo": "Dato malo — Background bloqueado",
}

TPI_INVENTORY_BUCKET_COLOR = {
    "disponible": "#1565C0",
    "asignado": "#6A1B9A",
    "malo": "#C62828",
}

TPI_KANBAN_COLUMNS = [
    ("dato_malo", "🚫 Dato malo (Background)"),
    ("solicitud", "📥 Solicitud"),
    ("asignada", "👷 Asignada"),
    ("en_proceso", "⚙️ En proceso"),
    ("en_revision", "🔍 En revisión"),
    ("listo_cuentas", "✅ Listo para cuentas"),
    ("cerrado", "📁 Cerrado"),
]
