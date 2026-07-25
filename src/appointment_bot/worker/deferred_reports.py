from __future__ import annotations

from appointment_bot.config import Settings
from appointment_bot.db.whatsapp_automation import enqueue_whatsapp_automation_job
from appointment_bot.domain import RunReport
from appointment_bot.services.notifier import notify_deferred_queue_summary
from appointment_bot.utils.screenshots import (
    remove_screenshot_paths,
    report_screenshot_paths,
)
from appointment_bot.worker.post_reservation_review import (
    replace_reports_with_reviewed_evidence,
)


class DeferredOrderReports:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._reports: list[RunReport] = []
        self._reviewed_order_ids: set[str] = set()

    def defer_if_needed(self, report: RunReport) -> None:
        if report.status in {
            "available",
            "partial",
            "registered",
            "reservation_unconfirmed",
        } or _has_final_submission_evidence(report):
            self._reports.append(report)
            return
        remove_screenshot_paths(report_screenshot_paths(report))

    def flush(self) -> None:
        if not self._reports:
            return
        reports = self._reports
        self._reports = []
        reviewed_order_ids = self._reviewed_order_ids
        self._reviewed_order_ids = set()
        summary = RunReport(
            status="completed",
            message="Evidencias diferidas del monitoreo.",
            exit_code=0,
        )
        notify_deferred_queue_summary(summary, self.settings, reports)
        for order_id in sorted(reviewed_order_ids):
            enqueue_whatsapp_automation_job(
                order_id,
                "reservation_album",
                settings=self.settings,
            )

    def replace_reviewed_evidence(self, review_results: list[dict[str, str]]) -> None:
        self._reports = replace_reports_with_reviewed_evidence(
            self._reports,
            review_results,
        )
        report_order_ids = {report.order_id for report in self._reports if report.order_id}
        self._reviewed_order_ids.update(
            result["order_id"]
            for result in review_results
            if result.get("status") == "completed"
            and result.get("order_id") in report_order_ids
        )


def _has_final_submission_evidence(report: RunReport) -> bool:
    details = report.details or {}
    return details.get("submission_outcome") in {"captcha_invalid", "slot_lost", "rejected"}
