import json
import logging
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult
from appointment_bot.services.detail_helpers import (
    appointment_datetime_details as _appointment_datetime_details,
)
from appointment_bot.utils.sanitization import sanitize_text
from appointment_bot.utils.screenshots import normalize_screenshot_paths

logger = logging.getLogger(__name__)

TELEGRAM_API_TIMEOUT_SECONDS = 15
TELEGRAM_URGENT_TIMEOUT_SECONDS = 5
TELEGRAM_TIMEZONE = ZoneInfo("America/Lima")


def notify_result(
    result: AvailabilityResult,
    settings: Settings,
    screenshot_path: Path | None = None,
    screenshot_paths: list[Path] | None = None,
) -> bool:
    message = f"[{result.status.upper()}] {result.message}"
    logger.info("%s", message)
    try:
        effective_screenshot_paths = normalize_screenshot_paths(
            screenshot_path,
            screenshot_paths,
        )

        if result.status in {
            "available",
            "unknown",
            "registered",
            "reservation_unconfirmed",
        }:
            return _send_result_notification(result, settings, effective_screenshot_paths)

        if result.status == "partial":
            if _should_notify_partial_result(result):
                return _send_result_notification(result, settings, effective_screenshot_paths)
            logger.info("Skipping Telegram notification for partial availability without hour.")
            return not settings.telegram_enabled

        if result.status == "unavailable":
            if _has_reservation_evidence(result) and effective_screenshot_paths:
                return _send_result_notification(
                    result,
                    settings,
                    effective_screenshot_paths,
                )
            if settings.telegram_notify_unavailable:
                return send_telegram_message(settings, _format_result_message(result))

        if result.status == "completed":
            if _programmed_details(result) is not None:
                return _send_programmed_sequence(
                    result,
                    settings,
                    effective_screenshot_paths,
                )
            if effective_screenshot_paths:
                return _send_telegram_photos(
                    settings,
                    effective_screenshot_paths,
                    _format_result_message(result),
                )
            logger.info("Appointment workflow is no longer available: %s", result.message)
        return not settings.telegram_enabled
    except Exception:
        # Una alerta secundaria nunca debe cambiar el resultado real de
        # una reserva que ya fue confirmada por la pagina.
        logger.exception("Unexpected error while sending result notification")
        return False


def notify_error(
    error: Exception,
    settings: Settings | None = None,
    screenshot_path: Path | None = None,
) -> None:
    message = f"[ERROR] {error}"
    logger.error("%s", message)

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
        except Exception:
            logger.exception("Unexpected error while sending error notification")


def send_telegram_message(
    settings: Settings,
    message: str,
    *,
    timeout_seconds: int = TELEGRAM_API_TIMEOUT_SECONDS,
) -> bool:
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
        with urlopen(request, timeout=timeout_seconds) as response:
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


def notify_immediate_availability(result: AvailabilityResult, settings: Settings) -> bool:
    if not _should_send_immediate_availability(result):
        return False
    return send_telegram_message(
        settings,
        _format_immediate_availability_message(result),
        timeout_seconds=TELEGRAM_URGENT_TIMEOUT_SECONDS,
    )


def notify_deferred_result(
    result: AvailabilityResult,
    settings: Settings,
    screenshot_path: Path | None = None,
    screenshot_paths: list[Path] | None = None,
) -> bool:
    effective_screenshot_paths = normalize_screenshot_paths(screenshot_path, screenshot_paths)
    return _send_result_notification(result, settings, effective_screenshot_paths)


def notify_deferred_queue_summary(
    report,
    settings: Settings,
    deferred_reports: list,
) -> bool:
    deferred_reports = [
        report
        for report in deferred_reports
        if report.status != "partial"
        or _should_notify_partial_result(
            AvailabilityResult(
                status=report.status,
                message=report.message,
                details=report.details,
            )
        )
    ]
    if not deferred_reports:
        return not settings.telegram_enabled

    if len(deferred_reports) == 1:
        item = deferred_reports[0]
        result = AvailabilityResult(
            status=item.status,
            message=item.message,
            details=item.details,
        )
        paths = [Path(path) for path in item.screenshot_paths or []]
        if not paths and item.screenshot_path:
            paths = [Path(item.screenshot_path)]
        return _send_deferred_result_notification(
            result,
            settings,
            _primary_evidence_paths(paths),
        )

    lines = [
        "Barrido de evidencias de la cola rapida.",
        "",
        report.message,
        "",
        f"Resultados con evidencia: {len(deferred_reports)}",
    ]
    delivered = send_telegram_message(settings, "\n".join(lines))
    for item in deferred_reports:
        result = AvailabilityResult(
            status=item.status,
            message=item.message,
            details=item.details,
        )
        paths = [Path(path) for path in item.screenshot_paths or []]
        if not paths and item.screenshot_path:
            paths = [Path(item.screenshot_path)]
        paths = _primary_evidence_paths(paths)
        delivered = _send_deferred_result_notification(result, settings, paths) or delivered
    return delivered


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
) -> bool:
    message = _format_telegram_result_message(result)
    if screenshot_paths:
        return _send_telegram_photos(settings, screenshot_paths, message)

    return send_telegram_message(settings, message)


def _send_deferred_result_notification(
    result: AvailabilityResult,
    settings: Settings,
    screenshot_paths: list[Path],
) -> bool:
    if _should_send_immediate_availability(result):
        if screenshot_paths:
            return _send_telegram_photos(
                settings,
                screenshot_paths,
                _format_deferred_evidence_caption(result),
            )
        return not settings.telegram_enabled
    return _send_result_notification(result, settings, screenshot_paths)


def _format_telegram_result_message(result: AvailabilityResult) -> str:
    if _should_send_immediate_availability(result):
        return _format_immediate_availability_message(result)
    return _format_result_message(result)


def _format_deferred_evidence_caption(result: AvailabilityResult) -> str:
    details = result.details or {}
    date, hour = _appointment_datetime_details(details)
    lines = ["Evidencia guardada del cupo detectado."]
    site = _format_availability_field(details.get("sede"))
    if site != "no registrado":
        lines.append(f"Sede: {site}")
    if date:
        lines.append(f"Fecha: {date}")
    if hour:
        lines.append(f"Hora: {hour}")
    return "\n".join(lines)


def _has_reservation_evidence(result: AvailabilityResult) -> bool:
    details = result.details or {}
    artifacts = details.get("diagnostic_artifacts")
    return bool(
        details.get("captcha_attempts")
        or details.get("submission_outcome") in {"slot_lost", "priority_deferred"}
        or (isinstance(artifacts, dict) and artifacts.get("captcha_images"))
    )


def _should_notify_partial_result(result: AvailabilityResult) -> bool:
    details = result.details or {}
    artifacts = details.get("diagnostic_artifacts")
    return bool(
        details.get("captcha_attempts")
        or details.get("submission_outcome")
        in {"blocked_by_order_rule", "priority_deferred"}
        or details.get("blocked_selected_for_evidence")
        or (isinstance(artifacts, dict) and artifacts.get("captcha_images"))
    )


def _should_send_immediate_availability(result: AvailabilityResult) -> bool:
    if result.status == "available":
        return True
    if result.status != "partial":
        return False

    details = result.details or {}
    date, hour = _appointment_datetime_details(details)
    if not date or not hour:
        return False
    return bool(
        details.get("blocked_by_order_rule")
        or details.get("blocked_selected_for_evidence")
        or details.get("submission_outcome") in {"blocked_by_order_rule", "priority_deferred"}
    )


def _primary_evidence_paths(image_paths: list[Path]) -> list[Path]:
    if not image_paths:
        return []
    for image_path in image_paths:
        lower_name = image_path.name.lower()
        if "captcha" not in lower_name:
            return [image_path]
    return [image_paths[0]]


def _send_telegram_photos(settings: Settings, image_paths: list[Path], caption: str) -> bool:
    if not image_paths:
        return False

    primary_delivered = send_telegram_photo(settings, image_paths[0], caption)
    if not primary_delivered:
        primary_delivered = send_telegram_message(settings, caption)

    for image_path in image_paths[1:]:
        send_telegram_photo(settings, image_path, "Evidencia adicional.")

    return primary_delivered


def _send_programmed_sequence(
    result: AvailabilityResult,
    settings: Settings,
    screenshot_paths: list[Path],
) -> bool:
    details = _programmed_details(result)
    if details is None:
        return False

    first_message = _format_programmed_greeting(details)
    payment_message = _format_programmed_payment_message(details)
    delivered = send_telegram_message(settings, first_message)

    if screenshot_paths:
        photo_caption = _format_programmed_photo_caption(details)
        delivered = send_telegram_photo(settings, screenshot_paths[0], photo_caption) or delivered
        for image_path in screenshot_paths[1:]:
            send_telegram_photo(settings, image_path, "Evidencia adicional.")
    else:
        delivered = (
            send_telegram_message(
                settings,
                _format_programmed_photo_caption(details),
            )
            or delivered
        )

    delivered = send_telegram_message(settings, payment_message) or delivered
    return delivered


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

    if result.status == "completed":
        programmed_message = _format_programmed_message(result)
        if programmed_message is not None:
            return programmed_message
        return (
            "Tramite ya completado o sin cita pendiente por reservar.\n\n"
            f"Detalle: {result.message}{details}"
        )

    return f"Revision completada con estado {result.status}.\n\nDetalle: {result.message}{details}"


def _format_immediate_availability_message(result: AvailabilityResult) -> str:
    details = result.details or {}
    date, hour = _appointment_datetime_details(details)
    date_options = _join_options(details.get("date_options"))
    hour_options = _join_options(details.get("hour_options"))
    slots = _format_slots(details.get("cupos") or details.get("slots"))
    sent_at = datetime.now(TELEGRAM_TIMEZONE).strftime("%H:%M:%S")
    lines = [
        "CUPO DETECTADO",
        f"Enviado: {sent_at} Lima",
        f"Sede: {_format_availability_field(details.get('sede'))}",
        f"Fechas: {_format_availability_field(date or date_options)}",
        f"Horas: {_format_availability_field(hour or hour_options)}",
        f"Cupos: {slots}",
    ]
    return "\n".join(lines)


def _format_availability_field(value: object) -> str:
    text = str(value or "").strip()
    return text or "no registrado"


def _format_slots(value: object) -> str:
    text = str(value or "").strip()
    return text or "no registrado"


def _format_registered_message(result: AvailabilityResult) -> str:
    details = result.details or {}
    person_name = details.get("nombre")
    site = details.get("sede")
    date, hour = _appointment_datetime_details(details)
    confirmation_source = str(details.get("confirmation_source") or "")

    if confirmation_source == "success_text_revalidation_inconclusive":
        heading = "Reserva registrada por el portal; validacion final pendiente."
        if person_name:
            heading = (
                f"Reserva registrada por el portal para {person_name}; "
                "validacion final pendiente."
            )
        lines = [
            heading,
            "",
            (
                "El portal mostro el mensaje de registro satisfactorio, pero no se pudo "
                "confirmar completamente la etapa Programado."
            ),
            (
                "Se guardo evidencia y el bot continuara con el siguiente usuario para "
                "no perder horarios."
            ),
        ]
        if date:
            lines.append(f"Fecha detectada: {date}")
        if hour:
            lines.append(f"Hora detectada: {hour}")
        if site:
            lines.append(f"Sede: {site}")
        lines.extend(
            [
                "",
                "Revisa la evidencia enviada para validar el estado final del tramite.",
            ]
        )
        return "\n".join(lines)

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


def _join_options(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value)


def _format_programmed_message(result: AvailabilityResult) -> str | None:
    details = _programmed_details(result)
    if details is None:
        return None

    heading = "Buenas noticias: encontramos y verificamos la cita programada."
    if details["person_name"]:
        heading = f"Buenas noticias: encontramos y verificamos la cita de {details['person_name']}."

    lines = [
        heading,
        "",
        "Ya figura como Programado en el portal PNP.",
    ]
    if details["date"]:
        lines.append(f"Fecha: {details['date']}")
    if details["hour"]:
        lines.append(f"Hora: {details['hour']}")
    if details["site"]:
        lines.append(f"Sede: {details['site']}")
    lines.extend(["", "Estado: listo para coordinar el pago y cerrar la atencion."])
    return "\n".join(lines)


def _programmed_details(result: AvailabilityResult) -> dict[str, object] | None:
    details = result.details or {}
    status = str(details.get("estado") or "").strip().casefold()
    if status != "programado":
        return None

    person_name = str(details.get("nombre") or details.get("cliente") or "").strip()
    if " | " in person_name:
        person_name = person_name.split(" | ", maxsplit=1)[0].strip()
    date, hour = _appointment_datetime_details(details)
    return {
        "person_name": person_name,
        "date": date,
        "hour": hour,
        "site": details.get("sede"),
    }


def _format_programmed_greeting(details: dict[str, object]) -> str:
    person_name = str(details.get("person_name") or "").strip()
    if person_name:
        return f"Hola, {person_name}. Ya logramos programar tu cita."
    return "Hola. Ya logramos programar tu cita."


def _format_programmed_photo_caption(details: dict[str, object]) -> str:
    lines = ["Te enviamos la constancia con la informacion de tu cita."]
    if details.get("date"):
        lines.append(f"Fecha: {details['date']}")
    if details.get("hour"):
        lines.append(f"Hora: {details['hour']}")
    if details.get("site"):
        lines.append(f"Sede: {details['site']}")
    return "\n".join(lines)


def _format_programmed_payment_message(details: dict[str, object]) -> str:
    return (
        "Ahora ya podemos proceder con el pago del servicio. "
        "Por favor coordina el abono para cerrar la atencion."
    )


def _format_result_details(result: AvailabilityResult) -> str:
    if not result.details:
        return ""

    lines = [f"{key.capitalize()}: {value}" for key, value in result.details.items()]
    return "\n\n" + "\n".join(lines)


def _format_error_message(error: Exception) -> str:
    return (
        "El bot encontro un error durante la revision.\n\n"
        f"Detalle: {sanitize_text(str(error))}\n\n"
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
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)
