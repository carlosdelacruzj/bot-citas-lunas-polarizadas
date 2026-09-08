from __future__ import annotations

from appointment_bot.core.models import RunReport
from appointment_bot.core.statuses import ResultStatus


def reservation_confirmed(report: RunReport) -> bool:
    if report.status == ResultStatus.REGISTERED or report.reservation_confirmed:
        return True
    if report.status != ResultStatus.COMPLETED:
        return False
    details = report.details or {}
    status = str(details.get("estado") or "").strip().casefold()
    date_text = str(details.get("fecha") or "").strip()
    return status == "programado" and bool(date_text)
