from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from typing import Any

from appointment_bot.db.monthly_dashboard_v2 import LIMA_TZ, monthly_dashboard_summary_v2
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.api.monthly_dashboard_routes import _shift_month


def monthly_dashboard_v2_payload(
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
    return HTTPStatus.OK, monthly_dashboard_summary_v2(
        month_start,
        _shift_month(month_start, 1),
        _shift_month(month_start, -1),
    )
