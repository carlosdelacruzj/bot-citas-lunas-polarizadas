from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.http import error_payload
from appointment_bot.services.api.opportunity_routes import (
    opportunity_burst_payload,
    opportunity_bursts_payload,
    opportunity_control_payload,
    update_opportunity_control_payload,
)
from appointment_bot.services.api.routing import ApiRequest


def get_opportunity_control(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = opportunity_control_payload()
    handler._send_json(status, payload)
    return


def get_opportunity_bursts(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = opportunity_bursts_payload(query)
    handler._send_json(status, payload)
    return


def get_opportunity_burst(request: ApiRequest) -> None:
    handler = request.transport
    burst_id = request.match
    if not burst_id:
        handler._send_json(
            HTTPStatus.NOT_FOUND,
            error_payload("not_found", "Rafaga no encontrada."),
        )
        return
    status, payload = opportunity_burst_payload(burst_id)
    handler._send_json(status, payload)
    return


def post_update_opportunity_control(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = update_opportunity_control_payload(
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return
