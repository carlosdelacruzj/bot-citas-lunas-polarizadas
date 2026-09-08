from __future__ import annotations

import re
from datetime import UTC, datetime, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from appointment_bot.utils.sanitization import sanitize_text

LIMA_TZ = ZoneInfo("America/Lima")
APPOINTMENT_DATETIME_RE = re.compile(
    r"^\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})(?:\s+(?P<hour>\d{1,2}:\d{2}))?\s*$"
)


def detail_text(value: Any, *, collapse_newlines: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        text = sanitize_text(str(value))
    else:
        text = sanitize_text(str(value).strip())
    if collapse_newlines:
        return text.replace("\n", " ").strip()
    return text


def detection_origin(details: dict[str, Any]) -> str:
    origin = detail_text(details.get("detection_origin"))
    if origin:
        return origin
    if details.get("fetch_probe"):
        return "fetch_probe"
    if details.get("reload_probe"):
        return "reload_probe"
    return "normal"


def parse_datetime(value: str | None, *, default_timezone: tzinfo = UTC) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=default_timezone)
    return parsed


def format_lima_datetime(
    value: str | None,
    *,
    default_timezone: tzinfo = UTC,
) -> str | None:
    parsed = parse_datetime(value, default_timezone=default_timezone)
    if parsed is None:
        return None
    return parsed.astimezone(LIMA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def appointment_datetime_details(
    details: dict[str, Any],
) -> tuple[object | None, object | None]:
    date = details.get("fecha")
    hour = details.get("hora")
    if not isinstance(date, str):
        return date, hour
    match = APPOINTMENT_DATETIME_RE.match(date)
    if match is None:
        return date, hour
    return match.group("date"), hour or match.group("hour")
