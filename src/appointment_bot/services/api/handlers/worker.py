from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.worker_routes import (
    health_payload,
    list_worker_commands_payload,
    worker_payload,
)


def get_health(request: ApiRequest) -> None:
    handler = request.transport
    controller = getattr(handler.server, "worker_controller", None)
    healthy, payload = health_payload(controller)
    handler._send_json(HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE, payload)
    return


def get_worker(request: ApiRequest) -> None:
    handler = request.transport
    handler._send_json(
        HTTPStatus.OK,
        worker_payload(getattr(handler.server, "worker_controller", None)),
    )
    return


def get_list_worker_commands(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    handler._send_json(HTTPStatus.OK, list_worker_commands_payload(query))
    return
