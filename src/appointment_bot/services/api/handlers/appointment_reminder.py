from __future__ import annotations

from appointment_bot.services.api.appointment_reminder_routes import appointment_reminders_payload
from appointment_bot.services.api.routing import ApiRequest


def get_appointment_reminders(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = appointment_reminders_payload()
    handler._send_json(status, payload)
    return
