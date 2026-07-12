"""Public core facade for pure models, statuses, and rules."""

from appointment_bot.core.contacts import (
    CONTACT_SOURCES,
    ContactValidationError,
    normalize_contact_name,
    normalize_contact_source,
    normalize_contact_whatsapp,
)
from appointment_bot.core.models import (
    AvailabilityResult,
    RunDetail,
    RunRecord,
    RunReport,
    RunSummary,
    ServiceOrderCandidate,
    ServiceOrderCreateResult,
    ServiceOrderRuntime,
    ServiceOrderSummary,
    WorkerCommand,
    WorkerState,
)
from appointment_bot.core.rules import (
    RESERVATION_RULE_TIMEZONE,
    ReservationConstraints,
    appointment_filter_from_constraints,
    appointment_matches_constraints,
    parse_appointment_date,
    parse_appointment_hour,
)
from appointment_bot.core.statuses import OrderStateStatus, ResultStatus, sanitize_details

__all__ = [
    "AvailabilityResult",
    "CONTACT_SOURCES",
    "ContactValidationError",
    "OrderStateStatus",
    "RESERVATION_RULE_TIMEZONE",
    "ReservationConstraints",
    "ResultStatus",
    "RunDetail",
    "RunRecord",
    "RunReport",
    "RunSummary",
    "ServiceOrderCandidate",
    "ServiceOrderCreateResult",
    "ServiceOrderRuntime",
    "ServiceOrderSummary",
    "WorkerCommand",
    "WorkerState",
    "appointment_filter_from_constraints",
    "appointment_matches_constraints",
    "normalize_contact_name",
    "normalize_contact_source",
    "normalize_contact_whatsapp",
    "parse_appointment_date",
    "parse_appointment_hour",
    "sanitize_details",
]
