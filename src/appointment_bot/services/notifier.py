import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from appointment_bot.config import Settings, load_settings
from appointment_bot.flows.appointments import AvailabilityResult
from appointment_bot.services.logger import setup_logging

logger = logging.getLogger(__name__)

TELEGRAM_API_TIMEOUT_SECONDS = 15


def notify_result(result: AvailabilityResult, settings: Settings) -> None:
    message = f"[{result.status.upper()}] {result.message}"
    print(message)

    if result.status in {"available", "partial", "unknown"}:
        send_telegram_message(settings, _format_result_message(result))
        return

    if result.status == "unavailable" and settings.telegram_notify_unavailable:
        send_telegram_message(settings, _format_result_message(result))


def notify_error(error: Exception, settings: Settings | None = None) -> None:
    message = f"[ERROR] {error}"
    print(message.encode("ascii", errors="replace").decode("ascii"))

    if settings is not None:
        send_telegram_message(settings, _format_error_message(error))


def send_telegram_message(settings: Settings, message: str) -> bool:
    if not settings.telegram_enabled:
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = urlencode(
        {
            "chat_id": settings.telegram_chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(url, data=payload, method="POST")

    try:
        with urlopen(request, timeout=TELEGRAM_API_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.warning("Could not send Telegram notification: %s", exc)
        return False

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError:
        logger.warning("Telegram returned a non-JSON response")
        return False

    if not data.get("ok"):
        logger.warning("Telegram rejected notification: %s", data)
        return False

    logger.info("Telegram notification sent")
    return True


def run_telegram_test() -> int:
    try:
        settings = load_settings()
        setup_logging(settings)
        if not settings.telegram_enabled:
            raise ValueError("TELEGRAM_ENABLED must be true to send a test message.")

        sent = send_telegram_message(
            settings,
            "Prueba de Telegram correcta.\n\n"
            "El bot ya puede enviarte avisos cuando detecte disponibilidad o errores.",
        )
        return 0 if sent else 1
    except Exception as exc:
        logger.exception("Telegram notification test failed")
        print(f"[ERROR] {exc}".encode("ascii", errors="replace").decode("ascii"))
        return 1


def format_heartbeat_message() -> str:
    return (
        "Bot activo.\n\n"
        "La ultima revision termino sin errores. Seguire revisando segun la programacion."
    )


def _format_result_message(result: AvailabilityResult) -> str:
    if result.status == "available":
        return (
            "Cita posiblemente disponible.\n\n"
            f"Detalle: {result.message}\n\n"
            "Revisa la pagina cuanto antes para confirmar manualmente."
        )

    if result.status == "partial":
        return (
            "Cambio detectado en la disponibilidad.\n\n"
            f"Detalle: {result.message}\n\n"
            "Puede ser una disponibilidad parcial. Conviene revisar manualmente."
        )

    if result.status == "unknown":
        return (
            "No pude interpretar el resultado de la pagina.\n\n"
            f"Detalle: {result.message}\n\n"
            "Revise la pagina y guarde un diagnostico para ajustar el bot si hace falta."
        )

    if result.status == "unavailable":
        return f"Revision completada: no hay cupos por ahora.\n\nDetalle: {result.message}"

    return f"Revision completada con estado {result.status}.\n\nDetalle: {result.message}"


def _format_error_message(error: Exception) -> str:
    return (
        "El bot encontro un error durante la revision.\n\n"
        f"Detalle: {error}\n\n"
        "Si se repite varias veces, el bot entrara en pausa automatica para no insistir."
    )
