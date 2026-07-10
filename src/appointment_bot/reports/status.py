"""Compatibility exports for status report rendering."""

from appointment_bot.services.status_reports import (
    StatusReportActivity,
    generate_daily_report_image,
    generate_status_report_images,
)

__all__ = [
    "StatusReportActivity",
    "generate_daily_report_image",
    "generate_status_report_images",
]
