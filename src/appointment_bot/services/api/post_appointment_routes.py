from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from appointment_bot.db.post_appointment import list_post_appointment_followups
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.post_appointment import (
    PostAppointmentReviewConflict,
    review_post_appointment_order,
)


def post_appointment_followups_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    return HTTPStatus.OK, list_post_appointment_followups()


def post_appointment_review_order_id(path: str) -> str | None:
    prefix = "/api/v1/service-orders/"
    suffix = "/post-appointment/review"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    order_id = unquote(path[len(prefix) : -len(suffix)]).strip()
    return order_id or None


def review_post_appointment_payload(order_id: str) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        item = review_post_appointment_order(order_id)
    except PostAppointmentReviewConflict as exc:
        return HTTPStatus.CONFLICT, error_payload("already_running", str(exc))
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))
    return HTTPStatus.OK, {
        "status": "reviewed",
        "message": "Seguimiento post-cita actualizado.",
        "followup": item,
    }
