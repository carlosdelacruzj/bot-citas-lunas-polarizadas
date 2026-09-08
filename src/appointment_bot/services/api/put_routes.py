from __future__ import annotations

from appointment_bot.services.api.handlers import whatsapp_message_template
from appointment_bot.services.api.routing import Route
from appointment_bot.services.api.whatsapp_message_template_routes import (
    whatsapp_message_template_action_path,
)

PUT_ROUTES = (
    Route(
        lambda path: whatsapp_message_template_action_path(path),
        whatsapp_message_template.put_update_whatsapp_message_template,
    ),
)
