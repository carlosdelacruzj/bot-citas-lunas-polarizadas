from __future__ import annotations

import logging
from http import HTTPStatus

from appointment_bot.config import load_settings
from appointment_bot.db.appointment_reminder_control import (
    REMINDER_LEAD_DAYS,
    REMINDER_MODES,
    AppointmentReminderControlConflict,
    update_appointment_reminder_control,
)
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.appointment_reminders import (
    appointment_reminder_status_payload,
    get_current_appointment_reminder_template,
    reminder_template_mentions_tomorrow,
)
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)


def appointment_reminders_payload() -> tuple[HTTPStatus, dict[str, object]]:
    try:
        settings = load_settings(require_login=False)
        return HTTPStatus.OK, appointment_reminder_status_payload(settings)
    except (RuntimeError, ValueError) as exc:
        logger.exception("Could not build appointment reminder status")
        return HTTPStatus.BAD_REQUEST, error_payload(
            "appointment_reminders_unavailable",
            sanitize_text(str(exc)),
        )


def update_appointment_reminders_payload(
    body: dict[str, object],
    *,
    requested_by: str | None,
) -> tuple[HTTPStatus, dict[str, object]]:
    settings = load_settings(require_login=False)
    mode = str(body.get("mode") or "").strip().lower()
    lead_days = body.get("lead_days")
    expected_revision = body.get("expected_revision")
    errors: dict[str, str] = {}
    if mode not in REMINDER_MODES:
        errors["mode"] = "Usa disabled, dry_run o live."
    if (
        not isinstance(lead_days, int)
        or isinstance(lead_days, bool)
        or lead_days not in REMINDER_LEAD_DAYS
    ):
        errors["lead_days"] = "Selecciona 1, 2 o 3 dias de anticipacion."
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
        errors["expected_revision"] = "La revisión esperada debe ser un entero."
    if (
        isinstance(lead_days, int)
        and not isinstance(lead_days, bool)
        and lead_days > 1
        and reminder_template_mentions_tomorrow(
            get_current_appointment_reminder_template(settings).message_template
        )
    ):
        errors["lead_days"] = (
            "La plantilla vigente dice 'mañana'. Actualízala en Mensajes antes de "
            "usar 2 o 3 días de anticipación."
        )
    if errors:
        payload = error_payload("bad_request", "Revisa la configuración del recordatorio.")
        payload["field_errors"] = errors
        return HTTPStatus.BAD_REQUEST, payload
    try:
        update_appointment_reminder_control(
            mode=mode,
            lead_days=int(lead_days),
            expected_revision=int(expected_revision),
            updated_by=requested_by or "dashboard-owner",
            settings=settings,
        )
    except AppointmentReminderControlConflict as exc:
        payload = error_payload("stale", str(exc))
        payload["current"] = appointment_reminder_status_payload(settings)
        return HTTPStatus.CONFLICT, payload
    return HTTPStatus.OK, appointment_reminder_status_payload(settings)


__all__ = ["appointment_reminders_payload", "update_appointment_reminders_payload"]
