from __future__ import annotations

from http import HTTPStatus

from appointment_bot.services.api.finance_routes import (
    create_finance_entry_payload,
    finance_categories_payload,
    finance_data_quality_payload,
    finance_entries_payload,
    finance_month_closure_payload,
    finance_summary_payload,
    reconcile_payment_amount_payload,
    update_finance_entry_payload,
    upsert_finance_month_closure_payload,
    void_finance_entry_payload,
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


def post_create_finance_entry(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = create_finance_entry_payload(handler._read_json())
    handler._send_json(status, payload)
    return


def post_update_finance_entry(request: ApiRequest) -> None:
    handler = request.transport
    finance_edit_id = request.match
    status, payload = update_finance_entry_payload(finance_edit_id, handler._read_json())
    handler._send_json(status, payload)
    return


def post_void_finance_entry(request: ApiRequest) -> None:
    handler = request.transport
    finance_void_id = request.match
    status, payload = void_finance_entry_payload(finance_void_id, handler._read_json())
    handler._send_json(status, payload)
    return


def post_upsert_finance_month_closure(request: ApiRequest) -> None:
    handler = request.transport
    status, payload = upsert_finance_month_closure_payload(
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return


def post_reconcile_payment_amount(request: ApiRequest) -> None:
    handler = request.transport
    finance_payment_id = request.match
    status, payload = reconcile_payment_amount_payload(
        finance_payment_id,
        handler._read_json(),
        requested_by=handler._authenticated_actor(),
    )
    handler._send_json(status, payload)
    return
