from __future__ import annotations

from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.whatsapp_message_template_routes import (
    whatsapp_message_templates_payload,
)


def get_whatsapp_message_templates(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = whatsapp_message_templates_payload()
    handler._send_json(status, payload)
    return
