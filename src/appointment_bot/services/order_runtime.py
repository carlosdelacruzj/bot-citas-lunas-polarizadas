from enum import StrEnum

from appointment_bot.core.models import RunReport
from appointment_bot.core.statuses import ResultStatus


class OrderReportOutcome(StrEnum):
    PAUSED = "paused"
    BLOCKED = "blocked"
    TERMINAL_STAGE = "terminal_stage"
    REGISTERED = "registered"
    RESERVATION_UNCONFIRMED = "reservation_unconfirmed"
    CAPTCHA_REJECTED = "captcha_rejected"
    ROUTINE = "routine"
    FAILURE = "failure"


ROUTINE_ORDER_STATUSES = {
    ResultStatus.UNAVAILABLE,
    ResultStatus.PARTIAL,
    ResultStatus.AVAILABLE,
    ResultStatus.COMPLETED,
}


def report_is_terminal_stage(report: RunReport) -> bool:
    details = report.details or {}
    status = str(details.get("estado") or "").strip().lower()
    return report.status == ResultStatus.COMPLETED and status in {"programado", "atendido"}


def order_done_status_from_report(report: RunReport) -> str:
    details = report.details or {}
    status = str(details.get("estado") or "").strip().lower()
    if status == "programado":
        return "programmed"
    return "completed"


def classify_order_report(report: RunReport) -> OrderReportOutcome:
    """Classify an order result once so every runner applies the same transition policy."""
    if report.status == ResultStatus.PAUSED:
        return OrderReportOutcome.PAUSED
    if bool((report.details or {}).get("blocked_by_order_rule")):
        return OrderReportOutcome.BLOCKED
    if report_is_terminal_stage(report):
        return OrderReportOutcome.TERMINAL_STAGE
    if report.status == ResultStatus.REGISTERED:
        return OrderReportOutcome.REGISTERED
    if report.status == ResultStatus.RESERVATION_UNCONFIRMED:
        return OrderReportOutcome.RESERVATION_UNCONFIRMED
    if str((report.details or {}).get("submission_outcome") or "") == "captcha_invalid":
        return OrderReportOutcome.CAPTCHA_REJECTED
    if report.status in ROUTINE_ORDER_STATUSES:
        return OrderReportOutcome.ROUTINE
    return OrderReportOutcome.FAILURE
