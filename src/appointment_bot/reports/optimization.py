"""Compatibility exports for optimization and partial-availability logs."""

from appointment_bot.services.optimization_log import (
    append_optimization_case,
    append_partial_availability_case,
)

__all__ = ["append_optimization_case", "append_partial_availability_case"]
