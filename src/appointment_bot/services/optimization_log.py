from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from appointment_bot.domain import ResultStatus, RunReport
from appointment_bot.services.reservation_timings import TIMING_DETAILS_KEY
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)

LIMA_TZ = ZoneInfo("America/Lima")
OPTIMIZATION_LOG_PATH = Path("docs/reservation-optimization-log.md")
PARTIAL_AVAILABILITY_LOG_PATH = Path("docs/partial-availability-log.md")
REJECTED_AFTER_SUBMISSION = {"captcha_invalid", "slot_lost", "rejected"}

_LAST_ORDER_FINISH: tuple[str, datetime] | None = None


def append_optimization_case(report: RunReport) -> None:
    """Append one curated optimization entry when a run reached a useful outcome."""
    global _LAST_ORDER_FINISH

    switch_context = _switch_context(report, _LAST_ORDER_FINISH)
    if report.order_id and report.finished_at:
        finished_at = _parse_datetime(report.finished_at)
        if finished_at is not None:
            _LAST_ORDER_FINISH = (report.order_id, finished_at)

    entry = _entry_for_report(report, switch_context=switch_context)
    if entry is None:
        return

    OPTIMIZATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        OPTIMIZATION_LOG_PATH.read_text(encoding="utf-8")
        if OPTIMIZATION_LOG_PATH.exists()
        else ""
    )
    if report.run_id and f"- Run: {report.run_id}" in existing:
        return

    with OPTIMIZATION_LOG_PATH.open("a", encoding="utf-8", newline="\n") as file:
        if not existing:
            file.write(_document_header())
        elif not existing.endswith("\n"):
            file.write("\n")
        file.write(entry)


def append_partial_availability_case(report: RunReport) -> None:
    """Append one curated entry for partial or rule-blocked availability."""
    entry = _partial_entry_for_report(report)
    if entry is None:
        return

    PARTIAL_AVAILABILITY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        PARTIAL_AVAILABILITY_LOG_PATH.read_text(encoding="utf-8")
        if PARTIAL_AVAILABILITY_LOG_PATH.exists()
        else ""
    )
    if report.run_id and f"- Run: {report.run_id}" in existing:
        return

    with PARTIAL_AVAILABILITY_LOG_PATH.open("a", encoding="utf-8", newline="\n") as file:
        if not existing:
            file.write(_partial_document_header())
        elif not existing.endswith("\n"):
            file.write("\n")
        file.write(entry)


def _partial_entry_for_report(report: RunReport) -> str | None:
    if not report.run_id or not report.order_id:
        return None
    details = report.details or {}
    if not _is_partial_availability_case(report, details):
        return None

    title_time = _format_lima_datetime(report.finished_at) or "hora no registrada"
    timing = details.get(TIMING_DETAILS_KEY)
    timing = timing if isinstance(timing, dict) else {}
    lines = [
        f"## {title_time} - {report.order_id} - {report.status.value}\n\n",
        f"- Run: {report.run_id}\n",
        f"- Orden: {_text(details.get('orden') or report.order_id)}\n",
        f"- Cliente: {_text(details.get('cliente')) or 'no registrado'}\n",
        f"- Cuenta: {_text(details.get('cuenta')) or 'no registrada'}\n",
        f"- Sede: {_text(details.get('sede') or details.get('site'))}\n",
        f"- Fecha detectada: {_text(details.get('fecha') or details.get('appointment_date'))}\n",
        f"- Hora detectada: {_text(details.get('hora') or details.get('appointment_hour'))}\n",
        f"- Cupos observados: {_text(details.get('cupos') or details.get('slots')) or 'no registrado'}\n",
        f"- Opciones fecha: {_text(_list_text(details.get('date_options')))}\n",
        f"- Opciones hora: {_text(_list_text(details.get('hour_options')))}\n",
        f"- Origen deteccion: {_detection_origin(details)}\n",
        f"- Resultado: {sanitize_text(report.message)}\n",
        "- Reglas/decision:\n",
        f"  - Bloqueado por regla: {_bool_text(details.get('blocked_by_order_rule'))}\n",
        "  - Seleccionado solo para evidencia: "
        f"{_bool_text(details.get('blocked_selected_for_evidence'))}\n",
        f"  - Outcome: {_text(details.get('submission_outcome')) or 'no aplicaba'}\n",
        f"  - Fecha del dia actual bloqueada: {_today_blocked_text(details)}\n",
        "- Contexto tecnico:\n",
        f"  - Modo monitoreo: {_text(details.get('monitoring_mode'))}\n",
        f"  - Reload probe: {_bool_text(details.get('reload_probe'))}\n",
        f"  - Fetch probe: {_bool_text(details.get('fetch_probe'))}\n",
        f"  - Refresco sede confirmado: {_bool_text(details.get('site_refresh_confirmed'))}\n",
        f"  - Refresco sede cambio opciones: {_bool_text(details.get('site_refresh_changed'))}\n",
        f"  - Refresco sede elapsed: {_milliseconds(details.get('site_refresh_elapsed_ms'))}\n",
        f"  - Duracion corrida: {_duration_text(report.duration_seconds)}\n",
        f"  - Seleccion fecha/hora: {_duration(timing, 'selection_seconds')}\n",
        "- Evidencia:\n",
        f"  - Screenshot principal: {_text(report.screenshot_path)}\n",
    ]
    diagnostic_artifacts = details.get("diagnostic_artifacts")
    if isinstance(diagnostic_artifacts, dict):
        for key, values in diagnostic_artifacts.items():
            if not isinstance(values, list):
                continue
            for value in values:
                lines.append(f"  - Diagnostico {key}: {_text(value)}\n")
    for path in _extra_screenshots(report):
        lines.append(f"  - Screenshot adicional: {_text(path)}\n")
    lines.extend(
        [
            "- Observacion tecnica:\n",
            f"  - {_partial_technical_observation(report, details)}\n\n",
        ]
    )
    return "".join(lines)


def _is_partial_availability_case(report: RunReport, details: dict[str, Any]) -> bool:
    status = ResultStatus(report.status)
    if status != ResultStatus.PARTIAL:
        return False
    date_text = _text(details.get("fecha") or details.get("appointment_date"))
    hour_text = _text(details.get("hora") or details.get("appointment_hour"))
    if _looks_like_no_slots(date_text) and _looks_like_no_slots(hour_text):
        return False
    return bool(
        date_text
        or hour_text
        or details.get("date_options")
        or details.get("hour_options")
    )


def _today_blocked_text(details: dict[str, Any]) -> str:
    if details.get("blocked_by_current_day") is True:
        return "si"
    date_text = _text(details.get("fecha") or details.get("appointment_date"))
    if not date_text:
        return "no registrado"
    finished_today = datetime.now(LIMA_TZ).strftime("%d/%m/%Y")
    return "probable" if finished_today in date_text else "no registrado"


def _partial_technical_observation(report: RunReport, details: dict[str, Any]) -> str:
    notes: list[str] = []
    origin = _detection_origin(details)
    date_text = _text(details.get("fecha") or details.get("appointment_date"))
    hour_text = _text(details.get("hora") or details.get("appointment_hour"))
    if origin == "fetch_probe":
        notes.append(
            "La senal parcial vino de fetch_probe; conviene medir si anticipa horas reales."
        )
    elif origin == "reload_probe":
        notes.append("La senal parcial aparecio despues de reload_probe.")
    else:
        notes.append("La senal parcial fue visible por el flujo normal.")
    if date_text and _looks_like_no_slots(hour_text):
        notes.append("Aparecio fecha sin hora seleccionable.")
    if details.get("blocked_by_order_rule"):
        notes.append("No se reservo porque la disponibilidad no cumplia reglas.")
    return " ".join(notes) or sanitize_text(report.message)


def _entry_for_report(
    report: RunReport,
    *,
    switch_context: str | None,
) -> str | None:
    if not report.run_id or not report.order_id or not _is_relevant_case(report):
        return None

    details = report.details or {}
    timing = details.get(TIMING_DETAILS_KEY)
    timing = timing if isinstance(timing, dict) else {}
    title_time = _format_lima_datetime(report.finished_at) or "hora no registrada"
    heading = f"## {title_time} - {report.order_id} - {report.status.value}\n\n"
    lines = [
        heading,
        f"- Run: {report.run_id}\n",
        f"- Corrida/attempt: {_text(details.get('observer_attempt') or details.get('attempt'))}\n",
        f"- Sede: {_text(details.get('sede') or details.get('site'))}\n",
        f"- Cita observada: {_appointment_text(details)}\n",
        f"- Cupos observados: {_text(details.get('cupos') or details.get('slots')) or 'no registrado'}\n",
        f"- Origen deteccion: {_detection_origin(details)}\n",
        f"- Resultado: {_result_summary(report)}\n",
        f"- Confirmacion posterior: {_post_confirmation(details)}\n",
        "- Tiempos:\n",
        f"  - Cupo detectado -> fin reserva: {_duration(timing, 'total_from_available_seconds')}\n",
        f"  - Seleccion fecha/hora: {_duration(timing, 'selection_seconds')}\n",
        f"  - Imagen CAPTCHA: {_duration(timing, 'captcha_image_seconds')}\n",
        f"  - 2captcha: {_duration(timing, 'captcha_solver_seconds')}\n",
        f"  - Llenar CAPTCHA -> click: {_duration(timing, 'captcha_fill_to_click_seconds')}\n",
        f"  - Click -> respuesta portal: {_duration(timing, 'click_to_portal_response_seconds')}\n",
        "  - Click -> screenshot confirmacion: "
        f"{_duration(timing, 'click_to_confirmation_screenshot_seconds')}\n",
        "- Contexto operativo:\n",
        f"  - Modo monitoreo: {_text(details.get('monitoring_mode'))}\n",
        f"  - Reload probe: {_bool_text(details.get('reload_probe'))}\n",
        f"  - Refresco sede confirmado: {_bool_text(details.get('site_refresh_confirmed'))}\n",
        f"  - Refresco sede cambio opciones: {_bool_text(details.get('site_refresh_changed'))}\n",
        f"  - Refresco sede elapsed: {_milliseconds(details.get('site_refresh_elapsed_ms'))}\n",
    ]
    if switch_context:
        lines.append(f"  - Cambio de usuario: {switch_context}\n")
    lines.extend(
        [
            "- Evidencia:\n",
            f"  - Screenshot principal: {_text(report.screenshot_path)}\n",
        ]
    )
    if details.get("captcha_solution_sent"):
        lines.append(f"  - CAPTCHA enviado: {_text(details.get('captcha_solution_sent'))}\n")
    if details.get("captcha_image_path"):
        lines.append(f"  - Imagen enviada a 2captcha: {_text(details.get('captcha_image_path'))}\n")
    captcha_attempts = details.get("captcha_attempts")
    if isinstance(captcha_attempts, list):
        for item in captcha_attempts:
            if not isinstance(item, dict):
                continue
            lines.append(
                "  - Intento CAPTCHA "
                f"{_text(item.get('attempt'))}: "
                f"outcome={_text(item.get('submission_outcome'))}, "
                f"valor={_text(item.get('captcha_solution_sent'))}, "
                f"duracion={_text(item.get('duration_seconds'))}s\n"
            )
            captcha_size = _dimensions(
                item.get("captcha_image_width"),
                item.get("captcha_image_height"),
            )
            captcha_css_size = _dimensions(
                item.get("captcha_element_css_width"),
                item.get("captcha_element_css_height"),
            )
            panel_size = _dimensions(
                item.get("captcha_panel_image_width"),
                item.get("captcha_panel_image_height"),
            )
            panel_css_size = _dimensions(
                item.get("captcha_panel_css_width"),
                item.get("captcha_panel_css_height"),
            )
            if captcha_size or captcha_css_size or panel_size or panel_css_size:
                lines.append(
                    "    - Medidas CAPTCHA: "
                    f"png={captcha_size or 'no registrado'}, "
                    f"css={captcha_css_size or 'no registrado'}, "
                    f"panel_png={panel_size or 'no registrado'}, "
                    f"panel_css={panel_css_size or 'no registrado'}, "
                    f"scale={_text(item.get('captcha_device_scale_factor'))}\n"
                )
            original_html_path = item.get("captcha_original_html_path")
            if original_html_path:
                original_size = _dimensions(
                    item.get("captcha_original_html_width"),
                    item.get("captcha_original_html_height"),
                )
                lines.append(
                    "    - CAPTCHA original HTML: "
                    f"path={_text(original_html_path)}, "
                    f"mime={_text(item.get('captcha_original_html_mime'))}, "
                    "formato_detectado="
                    f"{_text(item.get('captcha_original_html_detected_format'))}, "
                    f"bytes={_text(item.get('captcha_original_html_bytes'))}, "
                    f"dimensiones={original_size or 'no registrado'}\n"
                )
            elif item.get("captcha_original_html_source"):
                lines.append(
                    "    - CAPTCHA original HTML: "
                    f"source={_text(item.get('captcha_original_html_source'))}\n"
                )
    diagnostic_artifacts = details.get("diagnostic_artifacts")
    if isinstance(diagnostic_artifacts, dict):
        for key, values in diagnostic_artifacts.items():
            if not isinstance(values, list):
                continue
            for value in values:
                lines.append(f"  - Diagnostico {key}: {_text(value)}\n")
    for path in _extra_screenshots(report):
        lines.append(f"  - Screenshot adicional: {_text(path)}\n")
    lines.extend(
        [
            "- Observacion tecnica:\n",
            f"  - {_technical_observation(report, timing)}\n\n",
        ]
    )
    return "".join(lines)


def _is_relevant_case(report: RunReport) -> bool:
    details = report.details or {}
    status = ResultStatus(report.status)
    if report.reservation_confirmed or status == ResultStatus.REGISTERED:
        return True
    if _programmed_stage_confirmed(report):
        return True
    submission_outcome = str(details.get("submission_outcome") or "").strip()
    if status == ResultStatus.RESERVATION_UNCONFIRMED and _reached_final_submission(report):
        return True
    return submission_outcome in REJECTED_AFTER_SUBMISSION and _reached_final_submission(report)


def _reached_final_submission(report: RunReport) -> bool:
    details = report.details or {}
    timing = details.get(TIMING_DETAILS_KEY)
    marks = timing.get("marks_lima") if isinstance(timing, dict) else None
    return (
        report.reservation_attempted
        or bool(details.get("submission_outcome"))
        or (isinstance(marks, dict) and "reserve_click_started" in marks)
    )


def _programmed_stage_confirmed(report: RunReport) -> bool:
    if report.status != ResultStatus.COMPLETED:
        return False
    details = report.details or {}
    return str(details.get("estado") or "").strip().casefold() == "programado"


def _result_summary(report: RunReport) -> str:
    details = report.details or {}
    outcome = str(details.get("submission_outcome") or "").strip()
    if report.reservation_confirmed or report.status == ResultStatus.REGISTERED:
        source = _text(details.get("confirmation_source"))
        return f"Reserva registrada o confirmada por {source or 'confirmacion del flujo'}."
    if _programmed_stage_confirmed(report):
        return "Etapa Programado confirmada en una pasada posterior."
    if report.status == ResultStatus.RESERVATION_UNCONFIRMED:
        return "CAPTCHA resuelto, click en Reservar enviado, confirmacion inmediata no validada."
    if outcome in REJECTED_AFTER_SUBMISSION:
        return f"Envio final alcanzado, pero el portal respondio {outcome}."
    return sanitize_text(report.message)


def _post_confirmation(details: dict[str, Any]) -> str:
    source = _text(details.get("confirmation_source"))
    stage = _text(details.get("confirmacion_etapa") or details.get("estado"))
    if stage.casefold() == "programado":
        return "Programado detectado en esta corrida."
    if source:
        return f"Fuente registrada: {source}."
    return "No registrada en esta entrada."


def _technical_observation(report: RunReport, timing: dict[str, Any]) -> str:
    details = report.details or {}
    origin = _detection_origin(details)
    slowest = _slowest_timing(timing)
    notes: list[str] = []
    if origin == "normal":
        notes.append("El flujo normal detecto el cupo; reload_probe no fue necesario.")
    elif origin == "reload_probe":
        notes.append("La disponibilidad se detecto despues de reload_probe.")
    elif origin == "fetch_probe":
        notes.append("La disponibilidad se detecto por fetch_probe.")
    if report.status == ResultStatus.RESERVATION_UNCONFIRMED:
        notes.append("La confirmacion inmediata quedo debil y requiere revalidacion posterior.")
    if slowest:
        notes.append(f"El tramo mas lento fue {slowest}.")
    return " ".join(notes) or "Caso guardado por alcanzar un resultado util para optimizacion."


def _slowest_timing(timing: dict[str, Any]) -> str | None:
    labels = {
        "selection_seconds": "seleccion fecha/hora",
        "captcha_image_seconds": "imagen CAPTCHA",
        "captcha_solver_seconds": "2captcha",
        "captcha_fill_to_click_seconds": "llenar CAPTCHA -> click",
        "click_to_portal_response_seconds": "click -> respuesta portal",
        "click_to_confirmation_screenshot_seconds": "click -> screenshot confirmacion",
    }
    values: list[tuple[float, str]] = []
    for key, label in labels.items():
        value = _float(timing.get(key))
        if value is not None:
            values.append((value, label))
    if not values:
        return None
    seconds, label = max(values)
    return f"{label} ({seconds:.3f}s)"


def _switch_context(
    report: RunReport,
    previous: tuple[str, datetime] | None,
) -> str | None:
    if previous is None or not report.started_at or not report.order_id:
        return None
    previous_order_id, previous_finished_at = previous
    if previous_order_id == report.order_id:
        return None
    started_at = _parse_datetime(report.started_at)
    if started_at is None:
        return f"{previous_order_id} -> {report.order_id}"
    delta = max((started_at - previous_finished_at).total_seconds(), 0.0)
    return f"{previous_order_id} -> {report.order_id} en {delta:.3f}s"


def _appointment_text(details: dict[str, Any]) -> str:
    date = _text(details.get("fecha") or details.get("appointment_date"))
    hour = _text(details.get("hora") or details.get("appointment_hour"))
    if date and hour:
        return f"{date} {hour}"
    return date or hour or "no registrada"


def _detection_origin(details: dict[str, Any]) -> str:
    origin = _text(details.get("detection_origin"))
    if origin:
        return origin
    if details.get("fetch_probe"):
        return "fetch_probe"
    if details.get("reload_probe"):
        return "reload_probe"
    return "normal"


def _extra_screenshots(report: RunReport) -> list[str]:
    paths = report.screenshot_paths or []
    return [path for path in paths if path and path != report.screenshot_path]


def _format_lima_datetime(value: str | None) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone(LIMA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=LIMA_TZ)
    return parsed


def _duration(timing: dict[str, Any], key: str) -> str:
    value = _float(timing.get(key))
    return f"{value:.3f}s" if value is not None else "no registrado"


def _milliseconds(value: Any) -> str:
    if value in (None, ""):
        return "no registrado"
    return f"{value}ms"


def _duration_text(value: Any) -> str:
    number = _float(value)
    return f"{number:.3f}s" if number is not None else "no registrado"


def _dimensions(width: object, height: object) -> str:
    if width in {None, ""} or height in {None, ""}:
        return ""
    return f"{_text(width)}x{_text(height)}"


def _bool_text(value: Any) -> str:
    if value is True:
        return "si"
    if value is False:
        return "no"
    if value in (None, ""):
        return "no registrado"
    return str(value)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return sanitize_text(str(value)).replace("\n", " ").strip()


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value if _text(item))
    if isinstance(value, tuple):
        return ", ".join(_text(item) for item in value if _text(item))
    return _text(value)


def _looks_like_no_slots(value: str) -> bool:
    normalized = value.strip().casefold()
    return normalized in {"", "sin cupos", "0:sin cupos", "no registrado"}


def _document_header() -> str:
    return (
        "# Bitacora de optimizacion de reservas\n\n"
        "Archivo curado y automatico con casos de exito o casi-exito. "
        "No reemplaza PostgreSQL ni los logs completos; resume tiempos y evidencia util "
        "para mejorar el flujo sin guardar nombres completos ni credenciales.\n\n"
    )


def _partial_document_header() -> str:
    return (
        "# Bitacora de disponibilidad parcial\n\n"
        "Archivo curado y automatico para senales donde aparece fecha, hora parcial "
        "o disponibilidad bloqueada por regla sin llegar necesariamente a resolver CAPTCHA. "
        "Complementa la bitacora de optimizacion de reservas y ayuda a detectar patrones "
        "previos a cupos reales.\n\n"
    )
