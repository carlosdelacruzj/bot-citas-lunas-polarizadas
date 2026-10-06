from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.operator_inbox_routes import operator_inbox_payload
from appointment_bot.services.api.routing import ApiRequest


def get_operator_inbox(request: ApiRequest) -> None:
    handler = request.transport
    handler._send_json(HTTPStatus.OK, operator_inbox_payload())
    return
