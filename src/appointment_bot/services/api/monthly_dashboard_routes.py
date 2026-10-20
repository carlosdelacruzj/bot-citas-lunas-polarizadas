from __future__ import annotations

from datetime import date, datetime
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo

from appointment_bot.db.monthly_dashboard import monthly_dashboard_summary
from appointment_bot.services.api.http import error_payload

LIMA_TZ = ZoneInfo("America/Lima")


def monthly_dashboard_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    raw_month = query.get("month", [datetime.now(LIMA_TZ).strftime("%Y-%m")])[0].strip()
    try:
        month_start = datetime.strptime(raw_month, "%Y-%m").date().replace(day=1)
    except ValueError:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            "month must use YYYY-MM.",
            field_errors={"month": "Usa el formato YYYY-MM."},
        )
    next_month_start = _shift_month(month_start, 1)
    previous_month_start = _shift_month(month_start, -1)
    return HTTPStatus.OK, monthly_dashboard_summary(
        month_start,
        next_month_start,
        previous_month_start,
    )


def _shift_month(value: date, delta: int) -> date:
    month_index = value.year * 12 + value.month - 1 + delta
    return date(month_index // 12, month_index % 12 + 1, 1)
