from __future__ import annotations

import logging
from datetime import datetime, timedelta
from http import HTTPStatus
from zoneinfo import ZoneInfo

from appointment_bot.config import load_settings
from appointment_bot.db.appointment_reminder_control import (
    REMINDER_MODES,
    AppointmentReminderControlConflict,
    update_appointment_reminder_control,
)
from appointment_bot.db.appointment_reminders import list_appointment_reminder_candidates
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.appointment_reminders import (
    appointment_reminder_status_payload,
    validate_reminder_template,
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
    message_template = str(body.get("message_template") or "").strip()
    raw_ids = body.get("canary_order_ids")
    expected_revision = body.get("expected_revision")
    errors = validate_reminder_template(message_template)
    if mode not in REMINDER_MODES:
        errors["mode"] = "Usa disabled, dry_run, canary o live."
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
        errors["expected_revision"] = "La revisión esperada debe ser un entero."
    if not isinstance(raw_ids, list) or any(not isinstance(value, str) for value in raw_ids):
        errors["canary_order_ids"] = "Selecciona órdenes válidas de la lista de mañana."
        canary_order_ids: list[str] = []
    else:
        canary_order_ids = sorted({value.strip() for value in raw_ids if value.strip()})
    if len(canary_order_ids) > 2:
        errors["canary_order_ids"] = "El canario admite como máximo 2 órdenes."
    tomorrow = datetime.now(ZoneInfo("America/Lima")).date() + timedelta(days=1)
    eligible_ids = {
        candidate["order_id"]
        for candidate in list_appointment_reminder_candidates(tomorrow, settings=settings)
    }
    if set(canary_order_ids) - eligible_ids:
        errors["canary_order_ids"] = "Hay órdenes que ya no son elegibles para mañana."
    if mode == "canary" and not canary_order_ids:
        errors["canary_order_ids"] = "Selecciona 1 o 2 órdenes antes de activar el canario."
    if errors:
        payload = error_payload("bad_request", "Revisa la configuración del recordatorio.")
        payload["field_errors"] = errors
        return HTTPStatus.BAD_REQUEST, payload
    try:
        update_appointment_reminder_control(
            mode=mode,
            message_template=message_template,
            canary_order_ids=canary_order_ids,
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
