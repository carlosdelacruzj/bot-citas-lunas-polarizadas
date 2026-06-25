from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from appointment_bot.domain import RunReport
from appointment_bot.services.continuous_worker import ContinuousWorker
from appointment_bot.services.database_models import ServiceOrderRuntime, WorkerState
from appointment_bot.services.postgres_database import update_worker_state
from tests.helpers import make_settings


class ContinuousWorkerTests(unittest.TestCase):
    def test_unavailable_observer_rotates_without_sweeping_orders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            worker = ContinuousWorker(settings)
            worker._owner_token = "owner"
            order = ServiceOrderRuntime(
                order_id="order-1",
                name="Order 1",
                username="12345678",
                password="secret",
                priority=1,
                status="ready",
                created_at="2026-06-20T00:00:00+00:00",
                updated_at="2026-06-20T00:00:00+00:00",
            )
            with (
                patch(
                    "appointment_bot.services.continuous_worker.get_worker_state",
                    return_value=WorkerState(),
                ),
                patch(
                    "appointment_bot.services.continuous_worker.order_backoff_seconds",
                    return_value=0,
                ),
                patch(
                    "appointment_bot.services.continuous_worker.run_service_order",
                    return_value=RunReport(
                        status="unavailable",
                        message="none",
                        exit_code=0,
                    ),
                ) as run_order,
                patch("appointment_bot.services.continuous_worker.update_order_state"),
                patch.object(worker, "_set_session_state"),
                patch.object(worker, "_record_check"),
                patch.object(worker, "_reset_errors"),
                patch.object(worker, "_run_rapid_queue") as sweep,
            ):
                queue_requested = worker._monitor_order(order)

            effective_settings = run_order.call_args.args[0]
            self.assertEqual(effective_settings.monitor_window_seconds, 300)
            self.assertEqual(effective_settings.monitor_max_attempts, 5)
            self.assertEqual(effective_settings.monitor_interval_min_seconds, 60)
            self.assertEqual(effective_settings.monitor_interval_max_seconds, 75)
            self.assertTrue(run_order.call_args.kwargs["observer_mode"])
            self.assertFalse(queue_requested)
            sweep.assert_not_called()

    def test_health_detects_stalled_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            old = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
            update_worker_state(
                settings,
                phase="monitoring_observer",
                last_check_at=old,
            )
            worker = ContinuousWorker(settings)
            worker._running = True

            healthy, reason = worker.health()

            self.assertFalse(healthy)
            self.assertIn("worker_stalled", reason)

    def test_pause_and_resume_updates_are_serialized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worker = ContinuousWorker(make_settings(Path(directory)))
            pause_entered = threading.Event()
            release_pause = threading.Event()
            calls: list[str] = []

            def update_state(**values):
                calls.append(str(values["phase"]))
                if values["phase"] == "pausing":
                    pause_entered.set()
                    release_pause.wait(timeout=3)

            with patch.object(worker, "_update_state", side_effect=update_state):
                pause_thread = threading.Thread(target=worker.pause)
                resume_thread = threading.Thread(target=worker.resume)
                pause_thread.start()
                self.assertTrue(pause_entered.wait(timeout=2))
                resume_thread.start()
                time.sleep(0.05)
                self.assertEqual(calls, ["pausing"])
                release_pause.set()
                pause_thread.join(timeout=2)
                resume_thread.join(timeout=2)

            self.assertEqual(calls, ["pausing", "starting"])

    def test_resume_refreshes_health_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worker = ContinuousWorker(make_settings(Path(directory)))
            captured: dict[str, object] = {}

            def update_state(**values):
                captured.update(values)

            with patch.object(worker, "_update_state", side_effect=update_state):
                worker.resume()

            self.assertEqual(captured["phase"], "starting")
            self.assertIsNotNone(captured["last_check_at"])

    def test_worker_startup_refreshes_health_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            worker = ContinuousWorker(settings)
            worker.stop()

            with patch(
                "appointment_bot.services.continuous_worker.update_worker_state",
                wraps=update_worker_state,
            ) as update:
                worker.run_forever()

            startup_calls = [
                call.kwargs
                for call in update.call_args_list
                if call.kwargs.get("phase") == "starting"
            ]
            self.assertTrue(startup_calls)
            self.assertIsNotNone(startup_calls[0]["last_check_at"])


if __name__ == "__main__":
    unittest.main()
