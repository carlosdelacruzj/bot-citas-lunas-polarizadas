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


def post_appointment_followups_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        legacy_unpaged_request = not query
        limit = int(_query_value(query, "limit", "500" if legacy_unpaged_request else "10"))
        offset = int(_query_value(query, "offset", "0"))
        payload = list_post_appointment_followups(
            filter_name=_query_value(
                query,
                "filter",
                "all" if legacy_unpaged_request else "active",
            ),
            search=_query_value(query, "search", "")[:100],
            sort=_query_value(
                query,
                "sort",
                "legacy" if legacy_unpaged_request else "priority",
            ),
            direction=_query_value(query, "direction", "asc"),
            limit=limit,
            offset=offset,
            include_upcoming=_query_bool(query, "include_upcoming", False),
        )
    except (TypeError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.OK, payload


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


def _query_value(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    return str(values[0]).strip() if values else default


def _query_bool(query: dict[str, list[str]], key: str, default: bool) -> bool:
    value = _query_value(query, key, str(default).lower()).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{key} must be true or false.")
    return value == "true"
