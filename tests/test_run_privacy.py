from __future__ import annotations

import unittest
from unittest.mock import patch

from appointment_bot.core.models import RunDetail
from appointment_bot.services.api.run_routes import get_run_payload


class RunPrivacyTests(unittest.TestCase):
    @patch("appointment_bot.services.api.run_routes.get_run")
    def test_run_detail_api_does_not_return_historical_captcha_answer(self, get_run) -> None:
        get_run.return_value = RunDetail(
            run_id="run-1",
            order_id="order-1",
            status="registered",
            message="ok",
            exit_code=0,
            started_at="2026-09-01T10:00:00+00:00",
            finished_at="2026-09-01T10:01:00+00:00",
            duration_seconds=60,
            reservation_attempted=True,
            reservation_confirmed=True,
            screenshot_path=None,
            screenshot_count=0,
            created_at="2026-09-01T10:01:00+00:00",
            details={
                "captcha_solution_sent": "AB12",
                "captcha_attempts": [{"answer": "AB12", "attempt": 1}],
            },
            screenshot_paths=[],
        )

        status, payload = get_run_payload(
            "/api/v1/runs/run-1",
            {"include_details": ["true"]},
        )

        self.assertEqual(status, 200)
        self.assertNotIn("AB12", str(payload))


if __name__ == "__main__":
    unittest.main()
