from __future__ import annotations

import unittest

from appointment_bot.domain import (
    AvailabilityResult,
    ResultStatus,
)
from appointment_bot.reports.run_reporting import report_from_result


class DomainTests(unittest.TestCase):
    def test_statuses_are_normalized(self) -> None:
        result = AvailabilityResult(status="available", message="ok")
        self.assertIs(result.status, ResultStatus.AVAILABLE)

    def test_uncertain_reservation_has_error_exit_code(self) -> None:
        report = report_from_result(
            AvailabilityResult(status="reservation_unconfirmed", message="incierta")
        )
        self.assertEqual(report.exit_code, 1)

if __name__ == "__main__":
    unittest.main()
