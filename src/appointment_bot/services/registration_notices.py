from __future__ import annotations

from typing import Any

from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.core.registration_messages import (
    _monitoring_started_context,
    _registration_name_context,
    program_registration_context,
)
from appointment_bot.core.service_packages import (
    DEFAULT_RESERVATION_PRICE_TEXT,
    SERVICE_PACKAGE_STANDARD,
)
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
    service_type: str = "standard",
    service_package: str = SERVICE_PACKAGE_STANDARD,
    reservation_price: str = DEFAULT_RESERVATION_PRICE_TEXT,
    minimum_reservation_date: str | None = None,
    maximum_reservation_date: str | None = None,
    allowed_weekdays: tuple[int, ...] | None = None,
    excluded_date_ranges: tuple[dict[str, str], ...] = (),
    selected_program: dict[str, Any] | None = None,
    charge_required: bool = True,
    runtime_settings: RuntimeSettings,
) -> bool:
    if not recipient_phone and not recipient_username:
        return False
    template_key = REGISTRATION_NOTICE_TEMPLATE_KEYS[notice_type]
    template = get_whatsapp_message_template(template_key, settings=runtime_settings)
    definition = whatsapp_template_definition(template_key)
    if template is None or definition is None or not template.enabled:
        raise RuntimeError("La plantilla del aviso de registro no está disponible.")
    context = (
        _monitoring_started_context(
            display_name=display_name,
            service_type=service_type,
            service_package=service_package,
            reservation_price=reservation_price,
            minimum_reservation_date=minimum_reservation_date,
            maximum_reservation_date=maximum_reservation_date,
            allowed_weekdays=allowed_weekdays,
            excluded_date_ranges=excluded_date_ranges,
        )
        if notice_type == "monitoring_started"
        else _registration_name_context(display_name)
    )
    if notice_type == "monitoring_started" and selected_program is not None:
        context = program_registration_context(
            display_name or "", [selected_program], {
                str(selected_program["expediente"]): {
                    "service_type": service_type, "service_package": service_package,
                    "reservation_price": reservation_price, "charge_required": charge_required,
                    "minimum_reservation_date": minimum_reservation_date,
                    "maximum_reservation_date": maximum_reservation_date,
                    "allowed_weekdays": allowed_weekdays,
                    "excluded_date_ranges": excluded_date_ranges,
                },
            },
        )
    elif notice_type == "monitoring_started":
        context.update(
            placa="Por confirmar", expediente="Por confirmar",
            precio=f"S/{reservation_price}" if charge_required else "Sin cobro adicional",
        )
    message_text = render_whatsapp_template(
        definition,
        template.message_template,
        context,
        preserve_variables=frozenset({"expediente", "placa"}),
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
        settings=runtime_settings,
    )
__all__ = [
    "REGISTRATION_NOTICE_TEMPLATE_KEYS",
    "enqueue_registration_notice",
]
