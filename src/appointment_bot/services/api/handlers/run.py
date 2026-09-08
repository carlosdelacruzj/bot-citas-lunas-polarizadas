from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.run_routes import get_run_payload, list_runs_payload


def get_list_runs(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    handler._send_json(HTTPStatus.OK, list_runs_payload(query))
    return


def get_run(request: ApiRequest) -> None:
    handler = request.transport
    path = request.path
    query = request.query
    status, payload = get_run_payload(path, query)
    handler._send_json(status, payload)
    return
