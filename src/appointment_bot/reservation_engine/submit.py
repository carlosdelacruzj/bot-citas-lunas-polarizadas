"""Compatibility exports for reservation submission and evidence capture."""

from appointment_bot.reservation_engine.reservation_flow import (
    capture_blocked_captcha_evidence,
    complete_available_reservation,
)

__all__ = ["capture_blocked_captcha_evidence", "complete_available_reservation"]
