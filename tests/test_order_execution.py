from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from appointment_bot.core.models import RunReport, ServiceOrderRuntime
from appointment_bot.worker.order_execution import (
    DEFAULT_ORDER_EXECUTION_DEPENDENCIES,
    _appointment_filter_for_order,
)
from appointment_bot.worker.queue_traversal import (
    DEFAULT_QUEUE_TRAVERSAL_DEPENDENCIES,
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
            dependencies = replace(
                DEFAULT_ORDER_EXECUTION_DEPENDENCIES,
                get_reservation_constraints=Mock(
                    return_value=(minimum_date, None, None, ())
                ),
            )
            allowed = _appointment_filter_for_order(
                "order-1", settings, dependencies=dependencies
            )

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
            dependencies = replace(
                DEFAULT_ORDER_EXECUTION_DEPENDENCIES,
                get_reservation_constraints=Mock(
                    return_value=(minimum_date, None, None, ())
                ),
            )
            allowed = _appointment_filter_for_order(
                "order-1", settings, dependencies=dependencies
            )

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
            dependencies = replace(
                DEFAULT_ORDER_EXECUTION_DEPENDENCIES,
                get_reservation_constraints=Mock(
                    return_value=(None, None, (allowed_date.isoweekday(),), ())
                ),
            )
            allowed = _appointment_filter_for_order(
                "order-1", settings, dependencies=dependencies
            )

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
            run_order = Mock(side_effect=reports)
            dependencies = replace(
                DEFAULT_QUEUE_TRAVERSAL_DEPENDENCIES,
                list_active_orders=Mock(return_value=orders),
                claim_service_order=Mock(return_value=True),
                release_service_order_claim=Mock(return_value=True),
                update_order_state=Mock(),
                mark_order_done=Mock(),
                run_service_order=run_order,
                update_state_from_report=Mock(),
                delay_between_orders=Mock(),
            )
            report = run_rapid_queue_with_settings(settings, dependencies=dependencies)

            self.assertEqual(run_order.call_count, 3)
            self.assertEqual(report.status, "completed")
            self.assertEqual(report.details["checked_orders"], 3)

    def test_rapid_sweep_stops_after_unsafe_result(self) -> None:
        for unsafe_status in ("unknown", "reservation_unconfirmed"):
            with self.subTest(status=unsafe_status), tempfile.TemporaryDirectory() as directory:
                settings = make_settings(Path(directory))
                orders = [_order(1), _order(2)]
                run_order = Mock(
                    return_value=RunReport(
                        status=unsafe_status,
                        message="unsafe",
                        exit_code=1,
                    )
                )
                dependencies = replace(
                    DEFAULT_QUEUE_TRAVERSAL_DEPENDENCIES,
                    list_active_orders=Mock(return_value=orders),
                    claim_service_order=Mock(return_value=True),
                    release_service_order_claim=Mock(return_value=True),
                    update_order_state=Mock(),
                    mark_order_done=Mock(),
                    run_service_order=run_order,
                    update_state_from_report=Mock(),
                    delay_between_orders=Mock(),
                )
                report = run_rapid_queue_with_settings(
                    settings, dependencies=dependencies
                )

                self.assertEqual(run_order.call_count, 1)
                self.assertEqual(report.status, "error")


if __name__ == "__main__":
    unittest.main()
