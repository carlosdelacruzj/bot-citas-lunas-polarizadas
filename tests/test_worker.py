from __future__ import annotations

import tempfile
import threading
import time
import unittest
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from appointment_bot.services.continuous_worker import ContinuousWorker
from appointment_bot.services.database import get_worker_state, update_worker_state
from appointment_bot.services.runtime import LockBusyError
from tests.helpers import make_settings


class _RejectedLock(AbstractContextManager):
    def __enter__(self):
        raise LockBusyError("busy")

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class ContinuousWorkerTests(unittest.TestCase):
    def test_rejected_worker_does_not_overwrite_legitimate_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            update_worker_state(
                settings,
                phase="monitoring_observer",
                owner_token="legitimate",
            )
            worker = ContinuousWorker(settings)

            with patch(
                "appointment_bot.services.continuous_worker.single_run_lock",
                return_value=_RejectedLock(),
            ):
                with self.assertRaises(LockBusyError):
                    worker.run_forever()

            state = get_worker_state(settings)
            self.assertEqual(state.phase, "monitoring_observer")
            self.assertEqual(state.owner_token, "legitimate")

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
