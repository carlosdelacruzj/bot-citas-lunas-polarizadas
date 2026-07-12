"""Compatibility facade for queue traversal and single-order execution."""

# ruff: noqa: F401

from appointment_bot.db.orders import (
    claim_service_order,
    get_reservation_constraints_for_order,
    list_active_orders,
    release_service_order_claim,
    update_order_state,
)
from appointment_bot.worker import order_execution as _execution
from appointment_bot.worker import queue_traversal as _traversal

SERVICE_ORDER_LEASE_RENEW_INTERVAL_SECONDS = _execution.SERVICE_ORDER_LEASE_RENEW_INTERVAL_SECONDS
SERVICE_ORDER_LEASE_SECONDS = _execution.SERVICE_ORDER_LEASE_SECONDS
_CombinedEvent = _execution._CombinedEvent
_ServiceOrderLeaseHeartbeat = _execution._ServiceOrderLeaseHeartbeat
_delay_between_orders = _traversal._delay_between_orders
_reservation_limit_reached = _traversal._reservation_limit_reached
_update_state_from_report = _traversal._update_state_from_report


def _appointment_filter_for_order(order_id, settings):
    _execution.get_reservation_constraints_for_order = get_reservation_constraints_for_order
    return _execution._appointment_filter_for_order(order_id, settings)


def run_service_order(*args, **kwargs):
    _execution.get_reservation_constraints_for_order = get_reservation_constraints_for_order
    return _execution.run_service_order(*args, **kwargs)


def run_rapid_queue_with_settings(*args, **kwargs):
    _traversal.list_active_orders = list_active_orders
    _traversal.claim_service_order = claim_service_order
    _traversal.release_service_order_claim = release_service_order_claim
    _traversal.update_order_state = update_order_state
    _traversal.run_service_order = run_service_order
    _traversal._update_state_from_report = _update_state_from_report
    _traversal._delay_between_orders = _delay_between_orders
    return _traversal.run_rapid_queue_with_settings(*args, **kwargs)
