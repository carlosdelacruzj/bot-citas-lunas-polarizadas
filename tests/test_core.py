from __future__ import annotations

import unittest

from appointment_bot.core.models import AvailabilityResult
from appointment_bot.core.statuses import ResultStatus, sanitize_details
from appointment_bot.reports.run_reporting import report_from_result


class CoreTests(unittest.TestCase):
    def test_statuses_are_normalized(self) -> None:
        result = AvailabilityResult(status="available", message="ok")
        self.assertIs(result.status, ResultStatus.AVAILABLE)

    def test_uncertain_reservation_has_error_exit_code(self) -> None:
        report = report_from_result(
            AvailabilityResult(status="reservation_unconfirmed", message="incierta")
        )
        self.assertEqual(report.exit_code, 1)

    def test_general_report_removes_captcha_answers_recursively(self) -> None:
        report = report_from_result(
            AvailabilityResult(
                status="registered",
                message="ok",
                details={
                    "captcha_solution_sent": "AB12",
                    "nombre": "Cliente Uno",
                    "captcha_attempts": [
                        {
                            "external_answer": "AB12",
                            "captcha_solver_duration_ms": 1200,
                            "nested": {"answer": "AB12"},
                        }
                    ],
                    "reservation_timing": {"captcha_solver_seconds": 1.2},
                },
            )
        )

        self.assertNotIn("AB12", str(report.details))
        self.assertEqual(report.details["nombre"], "Cliente Uno")
        self.assertEqual(
            report.details["captcha_attempts"][0]["captcha_solver_duration_ms"],
            1200,
        )
        self.assertEqual(
            report.details["reservation_timing"]["captcha_solver_seconds"],
            1.2,
        )

    def test_detail_sanitizer_handles_nested_containers_and_binary_values(self) -> None:
        sanitized = sanitize_details(
            {
                "safe": ({"token_value": "secret", "kept": "ok"},),
                "binary": bytearray(b"captcha"),
            }
        )

        self.assertEqual(sanitized["safe"], [{"kept": "ok"}])
        self.assertEqual(sanitized["binary"], "[binary redacted]")

if __name__ == "__main__":
    unittest.main()
