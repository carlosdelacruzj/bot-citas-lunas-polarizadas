from __future__ import annotations

import unittest

from appointment_bot.domain import (
    AvailabilityResult,
    ResultStatus,
    RunReport,
    public_report_dict,
)
from appointment_bot.services.run_reporting import report_from_result


class DomainTests(unittest.TestCase):
    def test_statuses_are_normalized(self) -> None:
        result = AvailabilityResult(status="available", message="ok")
        self.assertIs(result.status, ResultStatus.AVAILABLE)

    def test_uncertain_reservation_has_error_exit_code(self) -> None:
        report = report_from_result(
            AvailabilityResult(status="reservation_unconfirmed", message="incierta")
        )
        self.assertEqual(report.exit_code, 1)

    def test_public_report_removes_sensitive_details_and_full_paths(self) -> None:
        report = RunReport(
            status="registered",
            message="ok",
            exit_code=0,
            details={"nombre": "Persona", "dni": "12345678", "fecha": "mañana"},
            screenshot_path=r"C:\private\screenshot.png",
        )
        payload = public_report_dict(report)
        self.assertEqual(payload["details"], {"fecha": "mañana"})
        self.assertEqual(payload["screenshot_path"], "screenshot.png")


if __name__ == "__main__":
    unittest.main()
