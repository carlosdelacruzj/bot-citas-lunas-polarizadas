"""Compatibility exports for reservation-attempt repositories."""

from appointment_bot.services.postgres_reservations import (
    create_reservation_attempt,
    get_active_reservation_attempt,
    mark_reservation_attempt_pending,
    resolve_reservation_attempt,
)

__all__ = [
    "create_reservation_attempt",
    "get_active_reservation_attempt",
    "mark_reservation_attempt_pending",
    "resolve_reservation_attempt",
]
