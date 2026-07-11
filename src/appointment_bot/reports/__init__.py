"""Public reports facade for the migration target package."""

from appointment_bot.reports.evidence import (
    EvidenceSummaryResult,
    append_evidence_case,
    export_evidence_summary,
)
from appointment_bot.reports.optimization import (
    append_optimization_case,
    append_partial_availability_case,
)
from appointment_bot.reports.run_reporting import (
    finalize_report,
    report_from_result,
    reservation_confirmed,
    settings_for_order,
)
from appointment_bot.reports.status import (
    StatusReportActivity,
    generate_daily_report_image,
    generate_status_report_images,
)

__all__ = [
    "EvidenceSummaryResult",
    "StatusReportActivity",
    "append_evidence_case",
    "append_optimization_case",
    "append_partial_availability_case",
    "export_evidence_summary",
    "finalize_report",
    "generate_daily_report_image",
    "generate_status_report_images",
    "report_from_result",
    "reservation_confirmed",
    "settings_for_order",
]
