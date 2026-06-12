import json
import logging
import mimetypes
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from appointment_bot.config import Settings, load_settings
from appointment_bot.flows.appointments import AvailabilityResult
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.runtime import RunTimeoutError

logger = logging.getLogger(__name__)

TELEGRAM_API_TIMEOUT_SECONDS = 15


def notify_result(
    result: AvailabilityResult,
    settings: Settings,
    screenshot_path: Path | None = None,
    screenshot_paths: list[Path] | None = None,
) -> None:
    message = f"[{result.status.upper()}] {result.message}"
    print(message)
    try:
        effective_screenshot_paths = _normalize_screenshot_paths(
            screenshot_path,
            screenshot_paths,
        )

        if result.status in {
            "available",
            "partial",
            "unknown",
            "registered",
            "reservation_unconfirmed",
        }:
            _send_result_notification(result, settings, effective_screenshot_paths)
            return

        if result.status == "unavailable" and settings.telegram_notify_unavailable:
            send_telegram_message(settings, _format_result_message(result))
            return

        if result.status == "completed":
            if effective_screenshot_paths:
                _send_telegram_photos(
                    settings,
                    effective_screenshot_paths,
                    _format_result_message(result),
                )
                return
            logger.info("Appointment workflow is no longer available: %s", result.message)
    except RunTimeoutError:
        raise
    except Exception:
        # TEMP REVIEW: Una alerta secundaria nunca debe cambiar el resultado real de
        # una reserva que ya fue confirmada por la pagina.
        logger.exception("Unexpected error while sending result notification")


def notify_error(
    error: Exception,
    settings: Settings | None = None,
    screenshot_path: Path | None = None,
) -> None:
    message = f"[ERROR] {error}"
    print(message.encode("ascii", errors="replace").decode("ascii"))

    if settings is not None:
        try:
            formatted = _format_error_message(error)
            if screenshot_path is not None and send_telegram_photo(
                settings,
                screenshot_path,
                formatted,
            ):
                return
            send_telegram_message(settings, formatted)
        except RunTimeoutError:
            raise
        except Exception:
            logger.exception("Unexpected error while sending error notification")


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
    except RunTimeoutError:
        raise
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


def send_telegram_photo(settings: Settings, image_path: Path, caption: str) -> bool:
    if not settings.telegram_enabled:
        return False

    if not image_path.exists():
        logger.warning("Telegram photo does not exist: %s", image_path)
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendPhoto"
    boundary = f"----appointment-bot-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    body = _multipart_form_data(
        boundary,
        fields={
            "chat_id": settings.telegram_chat_id,
            "caption": caption,
        },
        files={
            "photo": (image_path.name, content_type, image_path.read_bytes()),
        },
    )
    request = Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=TELEGRAM_API_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except RunTimeoutError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("Could not send Telegram photo: %s", exc)
        return False

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError:
        logger.warning("Telegram returned a non-JSON response for photo")
        return False

    if not data.get("ok"):
        logger.warning("Telegram rejected photo notification: %s", data)
        return False

    logger.info("Telegram photo sent: %s", image_path)
    return True


def _send_result_notification(
    result: AvailabilityResult,
    settings: Settings,
    screenshot_paths: list[Path],
) -> None:
    message = _format_result_message(result)
    if screenshot_paths:
        _send_telegram_photos(settings, screenshot_paths, message)
        return

    send_telegram_message(settings, message)


def _send_telegram_photos(settings: Settings, image_paths: list[Path], caption: str) -> bool:
    if not image_paths:
        return False

    primary_delivered = send_telegram_photo(settings, image_paths[0], caption)
    if not primary_delivered:
        primary_delivered = send_telegram_message(settings, caption)

    for image_path in image_paths[1:]:
        send_telegram_photo(settings, image_path, "Evidencia adicional del tramite.")

    return primary_delivered


def _normalize_screenshot_paths(
    screenshot_path: Path | None,
    screenshot_paths: list[Path] | None,
) -> list[Path]:
    paths = []
    if screenshot_path is not None:
        paths.append(screenshot_path)
    if screenshot_paths:
        paths.extend(screenshot_paths)

    unique_paths = []
    seen = set()
    for path in paths:
        path_key = str(path)
        if path_key in seen:
            continue
        seen.add(path_key)
        unique_paths.append(path)
    return unique_paths


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
    details = _format_result_details(result)
    if result.status == "available":
        return (
            "Cita posiblemente disponible.\n\n"
            f"Detalle: {result.message}{details}\n\n"
            "Revisa la pagina cuanto antes para confirmar manualmente."
        )

    if result.status == "registered":
        return _format_registered_message(result)

    if result.status == "reservation_unconfirmed":
        return (
            "Reserva no confirmada automaticamente.\n\n"
            f"Detalle: {result.message}{details}\n\n"
            "Revisa la pagina cuanto antes para confirmar el estado real de la cita."
        )

    if result.status == "partial":
        return (
            "Cambio detectado en la disponibilidad.\n\n"
            f"Detalle: {result.message}{details}\n\n"
            "Puede ser una disponibilidad parcial. Conviene revisar manualmente."
        )

    if result.status == "unknown":
        return (
            "No pude interpretar el resultado de la pagina.\n\n"
            f"Detalle: {result.message}{details}\n\n"
            "Revise la pagina y guarde un diagnostico para ajustar el bot si hace falta."
        )

    if result.status == "unavailable":
        return f"Revision completada: no hay cupos por ahora.\n\nDetalle: {result.message}{details}"

    return f"Revision completada con estado {result.status}.\n\nDetalle: {result.message}{details}"


def _format_registered_message(result: AvailabilityResult) -> str:
    details = result.details or {}
    person_name = details.get("nombre")
    site = details.get("sede")
    date = details.get("fecha")
    hour = details.get("hora")

    if person_name:
        heading = f"Estimado/a {person_name}, su cita ha sido reservada con exito."
    else:
        heading = "Su cita ha sido reservada con exito."

    lines = [heading]
    if date:
        lines.append(f"Fecha: {date}")
    if hour:
        lines.append(f"Hora: {hour}")
    if site:
        lines.append(f"Sede: {site}")

    if len(lines) == 1:
        return lines[0]

    return f"{lines[0]}\n\n" + "\n".join(lines[1:])


def _format_result_details(result: AvailabilityResult) -> str:
    if not result.details:
        return ""

    lines = [f"{key.capitalize()}: {value}" for key, value in result.details.items()]
    return "\n\n" + "\n".join(lines)


def _format_error_message(error: Exception) -> str:
    return (
        "El bot encontro un error durante la revision.\n\n"
        f"Detalle: {error}\n\n"
        "Si se repite varias veces, el bot entrara en pausa automatica para no insistir."
    )


def _multipart_form_data(
    boundary: str,
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, str, bytes]],
) -> bytes:
    chunks = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ]
        )

    for name, (filename, content_type, content) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)
