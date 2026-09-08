from __future__ import annotations

from appointment_bot.services.api.appointment_reminder_routes import (
    appointment_reminders_payload,
    update_appointment_reminders_payload,
)
from appointment_bot.services.api.routing import ApiRequest


def get_appointment_reminders(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = appointment_reminders_payload()
    handler._send_json(status, payload)
    return


def post_update_appointment_reminders(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = update_appointment_reminders_payload(
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return
