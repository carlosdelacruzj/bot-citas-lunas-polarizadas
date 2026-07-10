"""Compatibility exports for worker timing windows."""

from appointment_bot.worker.windows_runtime import (
    DAILY_CUTOFF_REASON,
    DAILY_CUTOFF_TIME,
    WORKER_TIMEZONE,
    HotWindowDecision,
    current_window_end,
    current_window_label,
    daily_cutoff_reached,
    extended_hot_window_until,
    hot_window_wait_decision,
    seconds_until_next_window,
)

__all__ = [
    "DAILY_CUTOFF_REASON",
    "DAILY_CUTOFF_TIME",
    "WORKER_TIMEZONE",
    "HotWindowDecision",
    "current_window_end",
    "current_window_label",
    "daily_cutoff_reached",
    "extended_hot_window_until",
    "hot_window_wait_decision",
    "seconds_until_next_window",
]
