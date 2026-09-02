from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as datetime_time
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings

WORKER_TIMEZONE = ZoneInfo("America/Lima")
DAILY_CUTOFF_REASON = "daily_cutoff"
SEARCH_WEEKDAYS = frozenset(range(6))


@dataclass(frozen=True)
class HotWindowDecision:
    should_wait: bool
    wait_seconds: int | None = None
    extended_until: datetime | None = None
    using_extension: bool = False


def daily_cutoff_reached(cutoff_time: datetime_time) -> bool:
    return datetime.now(WORKER_TIMEZONE).time() >= cutoff_time


def hot_window_wait_decision(
    settings: Settings,
    *,
    extended_until: datetime | None,
) -> HotWindowDecision:
    windows = settings.observer_hot_windows
    now = datetime.now(WORKER_TIMEZONE)
    if now.weekday() not in SEARCH_WEEKDAYS:
        return HotWindowDecision(
            should_wait=True,
            wait_seconds=random.randint(
                settings.outside_hot_window_min_seconds,
                settings.outside_hot_window_max_seconds,
            ),
            extended_until=None,
        )
    if not windows:
        return HotWindowDecision(should_wait=False, extended_until=extended_until)

    current = now.time()
    if any(start <= current < end for start, end in windows):
        return HotWindowDecision(should_wait=False, extended_until=extended_until)
    if extended_until is not None and now < extended_until:
        return HotWindowDecision(
            should_wait=False,
            extended_until=extended_until,
            using_extension=True,
        )

    seconds_to_window = seconds_until_next_window(now, windows)
    wait_seconds = min(
        random.randint(
            settings.outside_hot_window_min_seconds,
            settings.outside_hot_window_max_seconds,
        ),
        seconds_to_window,
    )
    return HotWindowDecision(
        should_wait=True,
        wait_seconds=wait_seconds,
        extended_until=None,
    )


def extended_hot_window_until(settings: Settings) -> datetime | None:
    extension_seconds = settings.observer_hot_window_extension_seconds
    if extension_seconds <= 0:
        return None
    now = datetime.now(WORKER_TIMEZONE)
    window_end = current_window_end(now, settings.observer_hot_windows)
    if window_end is None:
        return None
    return window_end + timedelta(seconds=extension_seconds)


def current_window_label(
    current: datetime_time,
    windows: tuple[tuple[datetime_time, datetime_time], ...],
) -> str | None:
    for start, end in windows:
        if start <= current < end:
            return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    return None


def seconds_until_next_window(
    now: datetime,
    windows: tuple[tuple[datetime_time, datetime_time], ...],
) -> int:
    candidates = []
    for days_ahead in range(8):
        candidate_date = now.date() + timedelta(days=days_ahead)
        if candidate_date.weekday() not in SEARCH_WEEKDAYS:
            continue
        candidates.extend(
            candidate
            for start, _ in windows
            if (candidate := datetime.combine(candidate_date, start, tzinfo=WORKER_TIMEZONE)) > now
        )
        if candidates:
            break
    return max(1, int((min(candidates) - now).total_seconds()))


def current_window_end(
    now: datetime,
    windows: tuple[tuple[datetime_time, datetime_time], ...],
) -> datetime | None:
    if now.weekday() not in SEARCH_WEEKDAYS:
        return None
    current = now.time()
    for start, end in windows:
        if start <= current < end:
            return datetime.combine(now.date(), end, tzinfo=WORKER_TIMEZONE)
    return None
