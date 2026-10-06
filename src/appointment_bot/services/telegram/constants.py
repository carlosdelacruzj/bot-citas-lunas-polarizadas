from __future__ import annotations

from zoneinfo import ZoneInfo

LIMA_TIMEZONE = ZoneInfo("America/Lima")


DEFAULT_ADMIN_API_URL = "http://127.0.0.1:8766"


DEFAULT_POLL_TIMEOUT_SECONDS = 30


RETRY_DELAY_SECONDS = 5


WORKER_MONITOR_INTERVAL_SECONDS = 300


WORKER_MONITOR_FAILURE_THRESHOLD = 3


WORKER_MONITOR_START_MINUTE = 7 * 60 + 30


WORKER_MONITOR_END_MINUTE = 18 * 60


CONFIRMATION_TTL_SECONDS = 120


CONVERSATION_TTL_SECONDS = 300


CAPTCHA_REVIEW_TTL_SECONDS = 600


NEW_CLIENT_CONVERSATION_TTL_SECONDS = 180


NEW_CLIENT_CONFIRMATION_TTL_SECONDS = 120


SENSITIVE_MESSAGE_TTL_SECONDS = 120


WORKER_COMMAND_TIMEOUT_SECONDS = 90


CLIENTS_PAGE_SIZE = 8


GENERAL_RATE_LIMIT = 30


MUTATION_RATE_LIMIT = 15


RATE_LIMIT_WINDOW_SECONDS = 60


MUTATING_COMMANDS = {
    "captchas",
    "cliente_nuevo",
    "pausar",
    "prioridad",
    "reanudar",
    "reglas_editar",
    "reiniciar",
    "oportunidad",
    "pago",
}


ORDER_TARGET_COMMANDS = {
    "cliente",
    "prioridad",
    "pago",
    "reglas",
    "reglas_editar",
}


HELP_TEXT = """Control remoto disponible:

/pendientes [pagina] - Bandeja de usuarios que requieren seguimiento
/cola [pagina] - Usuarios que estan buscando cupo
/cobros [pagina] - Pagos pendientes
/buscar TEXTO - Buscar cliente u orden
/cliente_nuevo - Registrar manualmente un cliente
/estado - Estado y controles del sistema
/cancelar - Cancelar la operacion guiada actual
/menu - Abrir el menu principal con botones
/ayuda - Mostrar esta ayuda

Historial, errores, CAPTCHA y controles avanzados estan en Herramientas dentro de /menu.
"""
