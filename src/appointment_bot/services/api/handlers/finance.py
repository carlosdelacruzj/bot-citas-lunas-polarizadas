from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.finance_routes import (
    finance_categories_payload,
    finance_data_quality_payload,
    finance_entries_payload,
    finance_month_closure_payload,
    finance_summary_payload,
)
from appointment_bot.services.api.routing import ApiRequest


def get_finance_categories(request: ApiRequest) -> None:
    handler = request.transport
    handler._send_json(HTTPStatus.OK, finance_categories_payload())
    return


def get_finance_entries(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = finance_entries_payload(query)
    handler._send_json(status, payload)
    return


def get_finance_summary(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = finance_summary_payload(query)
    handler._send_json(status, payload)
    return


def get_finance_data_quality(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = finance_data_quality_payload(query)
    handler._send_json(status, payload)
    return


def get_finance_month_closure(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    status, payload = finance_month_closure_payload(query)
    handler._send_json(status, payload)
    return
