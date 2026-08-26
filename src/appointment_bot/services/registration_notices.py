from __future__ import annotations

from datetime import date

from appointment_bot.config import Settings
from appointment_bot.core.whatsapp_message_templates import (
    render_whatsapp_template,
    whatsapp_template_definition,
)
from appointment_bot.db.whatsapp_automation import (
    RegistrationNoticeType,
    enqueue_registration_notice_job,
)
from appointment_bot.db.whatsapp_message_templates import get_whatsapp_message_template

REGISTRATION_NOTICE_TEMPLATE_KEYS: dict[RegistrationNoticeType, str] = {
    "monitoring_started": "registration_monitoring_started",
    "no_pending_request": "registration_no_pending_request",
    "invalid_credentials": "registration_invalid_credentials",
}


def enqueue_registration_notice(
    *,
    order_id: str,
    preflight_cycle: int,
    notice_type: RegistrationNoticeType,
    recipient_phone: str | None,
    recipient_username: str | None,
    display_name: str | None,
    settings: Settings,
    service_type: str = "standard",
    reservation_price: str = "50.00",
    minimum_reservation_date: str | None = None,
    maximum_reservation_date: str | None = None,
    allowed_weekdays: tuple[int, ...] | None = None,
    excluded_date_ranges: tuple[dict[str, str], ...] = (),
) -> bool:
    if not recipient_phone and not recipient_username:
        return False
    message_text = registration_notice_text(
        notice_type,
        display_name,
        service_type=service_type,
        reservation_price=reservation_price,
        minimum_reservation_date=minimum_reservation_date,
        maximum_reservation_date=maximum_reservation_date,
        allowed_weekdays=allowed_weekdays,
        excluded_date_ranges=excluded_date_ranges,
    )
    template_key = REGISTRATION_NOTICE_TEMPLATE_KEYS[notice_type]
    template = get_whatsapp_message_template(template_key, settings)
    definition = whatsapp_template_definition(template_key)
    if template is None or definition is None or not template.enabled:
        raise RuntimeError("La plantilla del aviso de registro no está disponible.")
    context = (
        _monitoring_started_context(
                display_name=display_name,
                service_type=service_type,
                reservation_price=reservation_price,
                minimum_reservation_date=minimum_reservation_date,
                maximum_reservation_date=maximum_reservation_date,
                allowed_weekdays=allowed_weekdays,
                excluded_date_ranges=excluded_date_ranges,
        )
        if notice_type == "monitoring_started"
        else _registration_name_context(display_name)
    )
    message_text = render_whatsapp_template(
        definition,
        template.message_template,
        context,
    )
    return enqueue_registration_notice_job(
        order_id=order_id,
        preflight_cycle=preflight_cycle,
        notice_type=notice_type,
        recipient_phone=recipient_phone,
        recipient_username=recipient_username,
        message_text=message_text,
        template_key=template.template_key,
        template_revision=template.revision,
        settings=settings,
    )


def registration_notice_text(
    notice_type: RegistrationNoticeType,
    display_name: str | None,
    *,
    service_type: str = "standard",
    reservation_price: str = "50.00",
    minimum_reservation_date: str | None = None,
    maximum_reservation_date: str | None = None,
    allowed_weekdays: tuple[int, ...] | None = None,
    excluded_date_ranges: tuple[dict[str, str], ...] = (),
) -> str:
    greeting = _greeting(display_name)
    if notice_type == "monitoring_started":
        return "\n\n".join(
            [
                greeting,
                "Pudimos ingresar correctamente y verificar tu solicitud ✅",
                "Tu solicitud quedó registrada y desde ahora comenzaremos con el monitoreo.",
                _service_summary_text(
                    service_type,
                    reservation_price,
                    minimum_reservation_date,
                    maximum_reservation_date,
                    allowed_weekdays,
                    excluded_date_ranges,
                ),
                "Buscaremos únicamente citas que cumplan estas condiciones. "
                "No reservaremos una fecha fuera de ellas.",
                "La disponibilidad depende de la PNP y no podemos garantizar que "
                "aparezca un cupo. Te escribiremos apenas consigamos la cita.",
            ]
        )
    if notice_type == "no_pending_request":
        return "\n\n".join(
            [
                greeting,
                "Pudimos ingresar correctamente, pero no encontramos una solicitud "
                "pendiente para reservar.",
                "Por favor, revisa si el trámite fue registrado y confírmanos cuando "
                "aparezca. Luego realizaremos una nueva validación.",
            ]
        )
    if notice_type == "invalid_credentials":
        return "\n\n".join(
            [
                greeting,
                "No pudimos validar el acceso con los datos registrados.",
                "Por seguridad realizamos un solo intento para evitar el bloqueo "
                "temporal de tu cuenta.",
                "Por favor, revisa el tipo y número de documento y la contraseña, y "
                "confírmanos los datos correctos para volver a validar.",
            ]
        )
    raise ValueError(f"Unsupported registration notice type: {notice_type}")


def _greeting(display_name: str | None) -> str:
    name = " ".join((display_name or "").split())
    return f"Hola, {name} 👋" if name else "Hola 👋"


def _service_summary_text(
    service_type: str,
    reservation_price: str,
    minimum_reservation_date: str | None,
    maximum_reservation_date: str | None,
    allowed_weekdays: tuple[int, ...] | None,
    excluded_date_ranges: tuple[dict[str, str], ...],
) -> str:
    amount = str(reservation_price or "50.00")
    label = _service_label(service_type)
    lines = [
        f"Servicio: {label}",
        f"Precio acordado: S/{amount}",
        "Condiciones de búsqueda: "
        + _search_conditions_text(
            minimum_reservation_date,
            maximum_reservation_date,
            allowed_weekdays,
        ),
    ]
    exclusions = _excluded_dates_text(excluded_date_ranges)
    if exclusions:
        lines.append(f"Fechas excluidas: {exclusions}")
    return "\n".join(lines)


def _monitoring_started_context(
    *,
    display_name: str | None,
    service_type: str,
    reservation_price: str,
    minimum_reservation_date: str | None,
    maximum_reservation_date: str | None,
    allowed_weekdays: tuple[int, ...] | None,
    excluded_date_ranges: tuple[dict[str, str], ...],
) -> dict[str, str]:
    name = " ".join((display_name or "").split())
    if not name:
        raise ValueError("El aviso de registro validado requiere el nombre del solicitante.")
    exclusions = _excluded_dates_text(excluded_date_ranges)
    return {
        "nombre": name,
        "servicio": _service_label(service_type),
        "monto": str(reservation_price or "50.00"),
        "condiciones": _search_conditions_text(
            minimum_reservation_date,
            maximum_reservation_date,
            allowed_weekdays,
        ),
        "fechas_excluidas": f"Fechas excluidas: {exclusions}" if exclusions else "",
    }


def _registration_name_context(display_name: str | None) -> dict[str, str]:
    name = " ".join((display_name or "").split())
    if not name:
        raise ValueError("El aviso de registro requiere un nombre para el saludo.")
    return {"nombre": name}


def _service_label(service_type: str) -> str:
    return {
        "selected_weekday": "Día elegido",
        "custom": "Personalizado",
    }.get(service_type, "Estándar")


def _weekday_name(value: int) -> str:
    return {
        1: "los lunes",
        2: "los martes",
        3: "los miércoles",
        4: "los jueves",
        5: "los viernes",
        6: "los sábados",
        7: "los domingos",
    }.get(int(value), "el día indicado")


def _search_conditions_text(
    minimum_date: str | None,
    maximum_date: str | None,
    allowed_weekdays: tuple[int, ...] | None,
) -> str:
    conditions = []
    if allowed_weekdays:
        weekday_names = [_weekday_name(day) for day in allowed_weekdays]
        if len(weekday_names) == 1:
            conditions.append(f"Solo {weekday_names[0]}")
        else:
            conditions.append("Días permitidos: " + ", ".join(weekday_names))
    if minimum_date and maximum_date:
        conditions.append(
            f"desde el {_display_date(minimum_date)} hasta el {_display_date(maximum_date)}"
        )
    elif minimum_date:
        conditions.append(f"a partir del {_display_date(minimum_date)}")
    elif maximum_date:
        conditions.append(f"hasta el {_display_date(maximum_date)}")
    if not conditions:
        return "Cualquier fecha disponible."
    return ", ".join(conditions) + "."


def _excluded_dates_text(excluded_date_ranges: tuple[dict[str, str], ...]) -> str:
    values = []
    for item in excluded_date_ranges:
        start = str(item.get("start_date") or "")
        end = str(item.get("end_date") or "")
        if not start or not end:
            continue
        if start == end:
            values.append(_display_date(start))
        else:
            values.append(f"{_display_date(start)} al {_display_date(end)}")
    return "; ".join(values)


def _display_date(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    except ValueError:
        return value


__all__ = [
    "REGISTRATION_NOTICE_TEMPLATE_KEYS",
    "enqueue_registration_notice",
    "registration_notice_text",
]
