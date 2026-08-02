from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from appointment_bot.core.models import RunReport, ServiceOrderRuntime
from appointment_bot.worker.queue_runtime import (
    _appointment_filter_for_order,
    run_rapid_queue_with_settings,
)
from tests.helpers import make_settings


def _order(index: int) -> ServiceOrderRuntime:
    return ServiceOrderRuntime(
        order_id=f"order-{index}",
        name=f"Order {index}",
        username=str(index),
        document_type="dni",
        password="secret",
        priority=0,
        status="ready",
        created_at="2026-06-20T00:00:00+00:00",
        updated_at="2026-06-20T00:00:00+00:00",
    )


class OrderExecutionTests(unittest.TestCase):
    def test_appointment_filter_blocks_dates_before_minimum_date(self) -> None:
        today = datetime.now(ZoneInfo("America/Lima")).date()
        minimum_date = today + timedelta(days=2)
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            with patch(
                "appointment_bot.worker.queue_runtime.get_reservation_constraints_for_order",
                return_value=(minimum_date, None, None, ()),
            ):
                allowed = _appointment_filter_for_order("order-1", settings)

            self.assertIsNotNone(allowed)
            assert allowed is not None
            self.assertFalse(
                allowed((minimum_date - timedelta(days=1)).strftime("%d/%m/%Y"), "12:00")
            )
            self.assertTrue(allowed(minimum_date.strftime("%d/%m/%Y"), "09:00"))
            self.assertTrue(
                allowed((minimum_date + timedelta(days=1)).strftime("%d/%m/%Y"), "09:00")
            )

    def test_appointment_filter_accepts_any_hour_for_an_allowed_date(self) -> None:
        today = datetime.now(ZoneInfo("America/Lima")).date()
        minimum_date = today + timedelta(days=2)
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            with patch(
                "appointment_bot.worker.queue_runtime.get_reservation_constraints_for_order",
                return_value=(minimum_date, None, None, ()),
            ):
                allowed = _appointment_filter_for_order("order-1", settings)

            self.assertIsNotNone(allowed)
            assert allowed is not None
            self.assertTrue(allowed(minimum_date.strftime("%d/%m/%Y"), "06:00"))
            self.assertTrue(allowed(minimum_date.strftime("%d/%m/%Y"), "18:00"))

    def test_appointment_filter_blocks_non_allowed_weekdays(self) -> None:
        today = datetime.now(ZoneInfo("America/Lima")).date()
        allowed_date = today + timedelta(days=1)
        blocked_date = allowed_date + timedelta(days=1)
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            with patch(
                "appointment_bot.worker.queue_runtime.get_reservation_constraints_for_order",
                return_value=(None, None, (allowed_date.isoweekday(),), ()),
            ):
                allowed = _appointment_filter_for_order("order-1", settings)

            self.assertIsNotNone(allowed)
            assert allowed is not None
            self.assertTrue(allowed(allowed_date.strftime("%d/%m/%Y"), "10:00"))
            self.assertFalse(allowed(blocked_date.strftime("%d/%m/%Y"), "10:00"))

    def test_rapid_sweep_continues_after_routine_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            orders = [_order(1), _order(2), _order(3)]
            reports = [
                RunReport(status="unavailable", message="none", exit_code=0),
                RunReport(status="partial", message="partial", exit_code=0),
                RunReport(status="completed", message="checked", exit_code=0),
            ]
            with (
                patch(
                    "appointment_bot.worker.queue_runtime.list_active_orders",
                    return_value=orders,
                ),
                patch(
                    "appointment_bot.worker.queue_runtime.claim_service_order",
                    return_value=True,
                ),
                patch(
                    "appointment_bot.worker.queue_runtime.release_service_order_claim",
                    return_value=True,
                ),
                patch(
                    "appointment_bot.worker.queue_runtime.run_service_order",
                    side_effect=reports,
                ) as run_order,
                patch("appointment_bot.worker.queue_runtime._update_state_from_report"),
                patch("appointment_bot.worker.queue_runtime._delay_between_orders"),
            ):
                report = run_rapid_queue_with_settings(settings)

            self.assertEqual(run_order.call_count, 3)
            self.assertEqual(report.status, "completed")
            self.assertEqual(report.details["checked_orders"], 3)

    def test_rapid_sweep_stops_after_unsafe_result(self) -> None:
        for unsafe_status in ("unknown", "reservation_unconfirmed"):
            with self.subTest(status=unsafe_status), tempfile.TemporaryDirectory() as directory:
                settings = make_settings(Path(directory))
                orders = [_order(1), _order(2)]
                with (
                    patch(
                        "appointment_bot.worker.queue_runtime.list_active_orders",
                        return_value=orders,
                    ),
                    patch(
                        "appointment_bot.worker.queue_runtime.claim_service_order",
                        return_value=True,
                    ),
                    patch(
                        "appointment_bot.worker.queue_runtime.release_service_order_claim",
                        return_value=True,
                    ),
                    patch(
                        "appointment_bot.worker.queue_runtime.run_service_order",
                        return_value=RunReport(
                            status=unsafe_status,
                            message="unsafe",
                            exit_code=1,
                        ),
                    ) as run_order,
                    patch("appointment_bot.worker.queue_runtime._update_state_from_report"),
                    patch("appointment_bot.worker.queue_runtime.update_order_state"),
                ):
                    report = run_rapid_queue_with_settings(settings)

                self.assertEqual(run_order.call_count, 1)
                self.assertEqual(report.status, "error")


if __name__ == "__main__":
    unittest.main()
