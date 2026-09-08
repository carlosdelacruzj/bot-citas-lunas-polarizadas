from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from appointment_bot.core.service_packages import (
    DEFAULT_RESERVATION_PRICE_TEXT,
    service_package_label,
)
from appointment_bot.services.telegram.constants import LIMA_TIMEZONE
from appointment_bot.services.telegram.models import PendingOrderChange
from appointment_bot.services.telegram.validation import _money_value
from appointment_bot.utils.sanitization import sanitize_text


def _main_menu_markup(counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = counts or {}
    pending_label = "Pendientes"
    queue_label = "Buscando cupo"
    payments_label = "Por cobrar"
    if "pending" in counts:
        pending_label += f" · {counts['pending']}"
    if "queue" in counts:
        queue_label += f" · {counts['queue']}"
    if "payments" in counts:
        payments_label += f" · {counts['payments']}"
    return {
        "inline_keyboard": [
            [
                {"text": pending_label, "callback_data": "ui:pending:1"},
                {"text": queue_label, "callback_data": "ui:queue:1"},
            ],
            [
                {"text": payments_label, "callback_data": "ui:payments:1"},
                {"text": "Nuevo cliente", "callback_data": "ui:manual:start"},
            ],
            [
                {"text": "Buscar", "callback_data": "ui:search:start"},
                {"text": "Citas y resumen", "callback_data": "ui:summary:show"},
            ],
            [
                {"text": "Estado", "callback_data": "ui:status:show"},
                {"text": "Herramientas", "callback_data": "ui:tools:show"},
            ],
        ]
    }


def _format_opportunity_control(control: dict[str, Any]) -> str:
    lines = [
        "CONTROL DE OPORTUNIDADES",
        "",
        f"Revision: {control.get('revision', 'desconocida')}",
    ]
    for target, label in (
        ("obs006", "Rafagas de oportunidad"),
        ("obs007", "Reobservacion de cupo perdido"),
    ):
        item = control.get(target)
        if not isinstance(item, dict):
            lines.append(f"{label}: sin datos")
            continue
        admissions = "si" if bool(item.get("admissions_allowed")) else "no"
        lines.append(
            f"{label}: deseado={item.get('desired_mode') or 'desconocido'} | "
            f"efectivo={item.get('effective_mode') or 'desconocido'} | admite={admissions}"
        )
    breaker = control.get("breaker")
    if isinstance(breaker, dict):
        lines.extend(
            [
                "",
                f"Breaker: {breaker.get('state') or 'desconocido'}",
                f"Motivo: {breaker.get('reason') or 'sin motivo activo'}",
            ]
        )
    active = control.get("active_burst")
    if isinstance(active, dict):
        lines.extend(
            [
                "",
                f"Rafaga activa: {active.get('burst_id') or 'sin id'}",
                f"Estado: {active.get('status') or 'desconocido'} | "
                f"sesiones max: {active.get('max_active_sessions') or 0} | "
                f"programados: {active.get('scheduled_clients') or 0}",
            ]
        )
    if bool(control.get("pending_application")):
        lines.extend(["", "Hay un cambio pendiente de aplicar por el worker."])
    return "\n".join(lines)


def _format_new_client_confirmation(values: dict[str, Any]) -> str:
    return (
        _format_manual_client_details(values, title="CONFIRMAR ALTA MANUAL")
        + "\n\nRevisa todos los datos antes de crear el cliente. "
        "La confirmacion vence en 2 minutos."
    )


def _format_manual_client_details(values: dict[str, Any], *, title: str) -> str:
    weekdays = values.get("allowed_weekdays")
    weekday_text = (
        ", ".join(_weekday_name(day) for day in weekdays)
        if isinstance(weekdays, (list, tuple)) and weekdays
        else "todos"
    )
    document_type = "DNI" if values.get("document_type") == "dni" else "CE"
    return "\n".join(
        [
            title,
            "",
            f"Tipo: {document_type}",
            f"Documento: {values.get('document_number') or 'no disponible'}",
            "Contrasena: registrada (oculta por seguridad)",
            f"Contacto: {values.get('contact_name') or 'no disponible'}",
            f"Fuente: {values.get('contact_source') or 'no disponible'}",
            "WhatsApp: "
            + str(
                values.get("contact_whatsapp")
                or values.get("contact_whatsapp_username")
                or "no registrado"
            ),
            "",
            "Servicio: "
            + _service_type_label(
                values.get("service_type"), values.get("service_package")
            ),
            "Precio acordado: S/"
            + str(values.get("reservation_price") or DEFAULT_RESERVATION_PRICE_TEXT),
            "Alcance: " + _service_scope_text(values),
            "",
            "Fecha minima: "
            + _format_operator_date(values.get("minimum_reservation_date")),
            "Fecha maxima: "
            + _format_operator_date(values.get("maximum_reservation_date")),
            f"Dias permitidos: {weekday_text}",
            "Fechas excluidas: "
            + _format_excluded_date_ranges(values.get("excluded_date_ranges")),
        ]
    )


def _service_type_label(value: Any, service_package: Any = None) -> str:
    return service_package_label(
        str(service_package) if service_package else None,
        str(value) if value else None,
    )


def _service_scope_text(values: dict[str, Any]) -> str:
    if values.get("service_type") != "selected_weekday":
        return "fecha compatible segun las restricciones indicadas"
    weekdays = values.get("allowed_weekdays") or []
    selected_weekday = _weekday_name(weekdays[0]) if weekdays else "dia indicado"
    return f"solo en {selected_weekday}; no reservar otro dia de la semana"


def format_order_detail(order: dict[str, Any]) -> str:
    applicant_name = _applicant_display_name(order)
    contact_name = _display_text(order.get("contact_name") or "Sin contacto", 60)
    lines = [
        "DETALLE DE ORDEN",
        "",
        f"Orden: {order.get('order_id') or 'desconocida'}",
        f"Cliente / titular: {applicant_name}",
        f"Tipo de documento: {order.get('document_type') or 'no disponible'}",
        f"Documento: {order.get('document_number_masked') or 'no disponible'}",
        "",
        f"Contacto: {contact_name}",
        "WhatsApp: "
        + str(
            order.get("contact_whatsapp_masked")
            or order.get("contact_whatsapp_username_masked")
            or "no registrado"
        ),
        f"Fuente: {order.get('contact_source') or 'no registrada'}",
        "",
        f"Estado: {_order_status_label(order.get('status'))}",
        f"Validacion: {_preflight_status_label(order.get('preflight_status'))}",
        f"Prioridad: {order.get('priority', 0)}",
        "Servicio: "
        + _service_type_label(order.get("service_type"), order.get("service_package")),
        "Precio acordado: S/"
        + str(order.get("reservation_price") or DEFAULT_RESERVATION_PRICE_TEXT),
        f"Reserva: {_reservation_status_label(order.get('reservation_status'))}",
        f"Pago: {_payment_status_label(order.get('payment_status'))}",
    ]
    if order.get("amount_agreed") is not None:
        agreed = _money_value(order.get("amount_agreed")) or Decimal("0")
        paid = _money_value(order.get("amount_paid")) or Decimal("0")
        lines.append(
            f"Cobro: acordado S/{_money_text(agreed)} | abonado S/{_money_text(paid)} | "
            f"saldo S/{_money_text(max(agreed - paid, Decimal('0')))}"
        )
    if order.get("reservation_date") or order.get("reservation_hour"):
        lines.append(
            "Cita: "
            f"{_format_operator_date(order.get('reservation_date'))} "
            f"{order.get('reservation_hour') or 'sin hora'}"
        )
    return "\n".join(lines)


def format_order_rules(order: dict[str, Any]) -> str:
    weekdays = order.get("allowed_weekdays")
    if isinstance(weekdays, list) and weekdays:
        weekday_text = ", ".join(_weekday_name(day) for day in weekdays)
    else:
        weekday_text = "todos"
    return "\n".join(
        [
            "REGLAS DE RESERVA",
            "",
            f"Orden: {order.get('order_id') or 'desconocida'}",
            "Fecha minima: "
            + _format_operator_date(order.get("minimum_reservation_date")),
            "Fecha maxima: "
            + _format_operator_date(order.get("maximum_reservation_date")),
            f"Dias permitidos: {weekday_text}",
            "Fechas excluidas: "
            + _format_excluded_date_ranges(order.get("excluded_date_ranges")),
        ]
    )


def _order_status_counts(orders: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"active": 0, "paused": 0, "payment_pending": 0, "closed": 0}
    for order in orders:
        status = str(order.get("status") or "")
        if status == "paused":
            counts["paused"] += 1
        elif status == "reserved_payment_pending":
            counts["payment_pending"] += 1
        elif status in {"archived", "paid", "completed", "no_charge"}:
            counts["closed"] += 1
        else:
            counts["active"] += 1
    return counts


def _order_status_label(value: Any) -> str:
    status = str(value or "")
    return {
        "ready": "Buscando cupo",
        "validation_pending": "Validando acceso",
        "paused": "Pausado",
        "reserved_payment_pending": "Reservado; pago pendiente",
        "paid": "Pagado",
        "completed": "Completado",
        "archived": "Archivado",
        "no_charge": "Cerrado sin cobro",
    }.get(status, status.replace("_", " ") or "Desconocido")


def _preflight_status_label(value: Any) -> str:
    status = str(value or "")
    return {
        "not_required": "No requerida",
        "pending": "Pendiente",
        "running": "En curso",
        "validated": "Acceso correcto",
        "failed": "Requiere revision",
    }.get(status, status.replace("_", " ") or "Desconocida")


def _reservation_status_label(value: Any) -> str:
    status = str(value or "")
    return {
        "pending": "Pendiente",
        "reserved": "Reservada",
        "confirmed": "Confirmada",
        "completed": "Completada",
        "unconfirmed": "Requiere revision",
    }.get(status, status.replace("_", " ") or "Sin reserva")


def _payment_status_label(value: Any) -> str:
    status = str(value or "")
    return {
        "pending": "Pendiente",
        "paid": "Pagado",
        "no_charge": "Sin cobro",
    }.get(status, status.replace("_", " ") or "Sin pago")


def _is_failed_run(run: dict[str, Any]) -> bool:
    try:
        exit_code = int(run.get("exit_code") or 0)
    except (TypeError, ValueError):
        exit_code = 0
    status = str(run.get("status") or "").lower()
    return exit_code != 0 or status in {
        "error",
        "failed",
        "unknown",
        "reservation_unconfirmed",
    }


def _safe_run_message(value: Any) -> str:
    text = sanitize_text(str(value or "Sin mensaje"))
    text = re.sub(r"(?i)[a-z]:[\\/][^\s]+", "[ruta]", text)
    text = re.sub(r"https?://\S+", "[url]", text)
    return _short_text(text, 160)


def _short_text(value: Any, limit: int) -> str:
    text = sanitize_text(" ".join(str(value).split()))
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _display_text(value: Any, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _applicant_display_name(order: dict[str, Any]) -> str:
    applicant_name = " ".join(str(order.get("applicant_name") or "").split())
    document_number = "".join(str(order.get("document_number") or "").split())
    masked_document = "".join(str(order.get("document_number_masked") or "").split())
    if not applicant_name:
        return "Titular no identificado por el portal"
    normalized_applicant = "".join(applicant_name.split())
    if document_number and normalized_applicant == document_number:
        return "Titular no identificado por el portal"
    if masked_document and normalized_applicant == masked_document:
        return "Titular no identificado por el portal"
    if re.fullmatch(r"\d{8,16}", normalized_applicant):
        return "Titular no identificado por el portal"
    return _display_text(applicant_name, 60)


def _money_text(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _weekday_name(value: Any) -> str:
    names = {
        1: "lunes",
        2: "martes",
        3: "miercoles",
        4: "jueves",
        5: "viernes",
        6: "sabado",
        7: "domingo",
    }
    try:
        return names.get(int(value), str(value))
    except (TypeError, ValueError):
        return "desconocido"


def _format_order_change_comparison(change: PendingOrderChange) -> str:
    if change.action == "priority":
        return (
            f"Orden: {change.order_id}\n"
            f"Prioridad anterior: {change.original['priority']}\n"
            f"Prioridad nueva: {change.updated['priority']}"
        )
    if change.action == "credentials":
        return (
            f"Cliente / titular: {change.original['applicant_name']}\n"
            f"Orden: {change.order_id}\n"
            "Cambio: reemplazar la contrasena del portal.\n\n"
            "La contrasena no se mostrara. La cuenta y sus subordenes quedaran "
            "pausadas hasta terminar una validacion automatica con el nuevo acceso."
        )
    if change.action in {"payment_paid", "payment_partial"}:
        consequence = (
            "Al confirmar, se guardara el abono y el cobro seguira pendiente. "
            "No se encolara el postpago."
            if change.action == "payment_partial"
            else "Al confirmar, el pago pasara a paid y se encolara automaticamente "
            "el seguimiento postpago por WhatsApp."
        )
        return (
            f"Cliente / titular: {change.original['applicant_name']}\n"
            f"Orden: {change.order_id}\n"
            f"Monto acordado: S/{change.updated['amount_agreed']}\n"
            f"Registrado anteriormente: S/{change.original['amount_paid']}\n"
            f"Total que quedara pagado: S/{change.updated['amount_paid']}\n\n"
            f"{consequence}"
        )
    return "\n".join(
        [
            f"Orden: {change.order_id}",
            "",
            "Fecha minima: "
            + _change_value(change.original, change.updated, "minimum_reservation_date"),
            "Fecha maxima: "
            + _change_value(change.original, change.updated, "maximum_reservation_date"),
            f"Dias: {_change_value(change.original, change.updated, 'allowed_weekdays')}",
            "Fechas excluidas: "
            + _change_value(change.original, change.updated, "excluded_date_ranges"),
        ]
    )


def _change_value(original: dict[str, Any], updated: dict[str, Any], field: str) -> str:
    old = original.get(field)
    new = updated.get(field)
    if field in {"minimum_reservation_date", "maximum_reservation_date"}:
        return f"{_format_operator_date(old)} -> {_format_operator_date(new)}"
    if field == "excluded_date_ranges":
        return f"{_format_excluded_date_ranges(old)} -> {_format_excluded_date_ranges(new)}"
    if field == "allowed_weekdays":
        old_days = ", ".join(_weekday_name(day) for day in (old or [])) or "todos"
        new_days = ", ".join(_weekday_name(day) for day in (new or [])) or "todos"
        return f"{old_days} -> {new_days}"
    old_text = old if old is not None else "sin limite"
    new_text = new if new is not None else "sin limite"
    return f"{old_text} -> {new_text}"


def _format_operator_date(value: Any) -> str:
    if value in {None, ""}:
        return "sin limite"
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return "fecha invalida"
    return parsed.strftime("%d-%m-%Y")


def _format_excluded_date_ranges(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "ninguna"
    labels = []
    for item in value:
        if not isinstance(item, dict):
            continue
        start = _format_operator_date(item.get("start_date"))
        end = _format_operator_date(item.get("end_date"))
        labels.append(start if start == end else f"{start} al {end}")
    return "; ".join(labels) if labels else "ninguna"


def _format_worker_command_success(
    command: str,
    operation_id: str,
    worker: dict[str, Any],
) -> str:
    phase = str(worker.get("phase") or "desconocida")
    if command == "pause":
        result = "Worker pausado correctamente."
    elif command == "resume":
        result = "Worker reanudado correctamente."
    else:
        result = "Worker reiniciado y recuperado correctamente."
    return f"{result}\nSolicitud: {operation_id}\nFase actual: {phase}"


def _worker_command_label(command: str) -> str:
    return {
        "pause": "pausar el worker",
        "resume": "reanudar el worker",
        "restart": "reiniciar el worker",
    }[command]


def format_worker_status(payload: dict[str, Any]) -> str:
    worker_running = bool(payload.get("worker_running"))
    phase = str(payload.get("phase") or "desconocida")
    paused = bool(payload.get("paused"))
    if worker_running and phase == "outside_hot_window":
        summary = "Activo, esperando la siguiente ventana de trabajo."
    elif worker_running and paused:
        summary = "Activo, pero pausado administrativamente."
    elif worker_running:
        summary = "Activo."
    else:
        summary = "Worker sin lease activo; el supervisor deberia recuperarlo."
    lines = [
        "ESTADO DEL SISTEMA",
        "",
        summary,
        f"Fase: {phase}",
        f"Pausado: {'si' if paused else 'no'}",
    ]
    current_order = payload.get("current_order_id")
    if current_order:
        lines.append(f"Orden actual: {current_order}")
    last_check = _format_lima_datetime(payload.get("last_check_at"))
    next_check = _format_lima_datetime(payload.get("next_check_at"))
    if last_check:
        lines.append(f"Ultima revision: {last_check}")
    if next_check:
        lines.append(f"Proxima revision: {next_check}")
    errors = int(payload.get("consecutive_errors") or 0)
    lines.append(f"Errores consecutivos: {errors}")
    if payload.get("last_error"):
        lines.append("Ultimo error: disponible en el dashboard.")
    return "\n".join(lines)


def _format_lima_datetime(value: Any) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(LIMA_TIMEZONE).strftime("%d-%m-%Y %H:%M:%S")
    except ValueError:
        return None
