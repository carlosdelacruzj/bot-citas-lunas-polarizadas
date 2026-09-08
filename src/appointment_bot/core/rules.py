from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

RESERVATION_RULE_TIMEZONE = ZoneInfo("America/Lima")


@dataclass(frozen=True)
class ReservationConstraints:
    minimum_date: date | None = None
    maximum_date: date | None = None
    allowed_weekdays: tuple[int, ...] | None = None
    excluded_date_ranges: tuple[tuple[date, date], ...] = ()


def appointment_filter_from_constraints(
    constraints: ReservationConstraints,
    *,
    current_reservation_date: date | None = None,
) -> Callable[[str, str], bool]:
    effective_current_date = (
        current_reservation_date
        if current_reservation_date is not None
        else datetime.now(RESERVATION_RULE_TIMEZONE).date()
    )

    def is_allowed(date_text: str, hour_text: str) -> bool:
        return appointment_matches_constraints(
            date_text,
            hour_text,
            constraints,
            current_reservation_date=effective_current_date,
        )

    return is_allowed


def appointment_matches_constraints(
    date_text: str,
    hour_text: str,
    constraints: ReservationConstraints,
    *,
    current_reservation_date: date,
) -> bool:
    parsed_date = parse_appointment_date(date_text)
    if parsed_date is None or parsed_date <= current_reservation_date:
        return False
    if constraints.minimum_date is not None and parsed_date < constraints.minimum_date:
        return False
    if constraints.maximum_date is not None and parsed_date > constraints.maximum_date:
        return False
    if any(
        start_date <= parsed_date <= end_date
        for start_date, end_date in constraints.excluded_date_ranges
    ):
        return False
    if (
        constraints.allowed_weekdays is not None
        and parsed_date.isoweekday() not in constraints.allowed_weekdays
    ):
        return False
    return True


def parse_appointment_date(date_text: str) -> date | None:
    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", date_text)
    if match is None:
        return None
    day, month, year = (int(item) for item in match.groups())
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


def parse_appointment_time(hour_text: str) -> tuple[int, int] | None:
    match = re.search(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\b", hour_text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


__all__ = [
    "RESERVATION_RULE_TIMEZONE",
    "ReservationConstraints",
    "appointment_filter_from_constraints",
    "appointment_matches_constraints",
    "parse_appointment_date",
    "parse_appointment_time",
]
