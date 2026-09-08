from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from appointment_bot.core.models import RunReport
from appointment_bot.db.orders import (
    claim_service_order,
    mark_order_submission_intent,
    mark_order_submission_pending,
    order_reservation_pending,
    set_order_paused,
)
from appointment_bot.db.reservations import (
    create_reservation_attempt,
    mark_reservation_attempt_pending,
    resolve_reservation_attempt,
)
from appointment_bot.services.application.create_service_order import create_service_order
from appointment_bot.services.order_transitions import (
    order_can_submit,
    reconcile_pending_submission,
)
from tests.helpers import database_connection, make_settings


class OrderTransitionTests(unittest.TestCase):
    def _create_active_attempt(
        self,
        settings,
        order_id: str,
        *,
        status: str = "pending",
    ) -> str:
        attempt_id = f"attempt-{status}-{order_id}"
        create_reservation_attempt(
            attempt_id,
            order_id,
            details={"fecha": "15/09/2026", "hora": "10:30", "sede": "Lima"},
            settings=settings.runtime,
        )
        mark_order_submission_intent(order_id, settings=settings.runtime)
        if status in {"pending", "unknown"}:
            mark_reservation_attempt_pending(attempt_id, settings=settings.runtime)
            mark_order_submission_pending(order_id, settings=settings.runtime)
        if status == "unknown":
            resolve_reservation_attempt(attempt_id, "unknown", settings=settings.runtime)
        return attempt_id

    def test_invalid_attempt_resolution_status_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid reservation attempt status"):
            resolve_reservation_attempt("attempt-1", "retryable")

    def test_paused_order_cannot_submit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="password",
                applicant_name="Test",
                priority=1,
                require_preflight=False,
                runtime_settings=settings.runtime,
            )
            owner = "test-worker"
            self.assertTrue(
                claim_service_order(
                    result.order_id, owner_token=owner, lease_seconds=60, settings=settings.runtime
                )
            )

            self.assertTrue(
                order_can_submit(result.order_id, owner, runtime_settings=settings.runtime)
            )

            set_order_paused(result.order_id, True, settings=settings.runtime)

            self.assertFalse(
                order_can_submit(result.order_id, owner, runtime_settings=settings.runtime)
            )

    def test_old_pending_submission_remains_blocked_without_authoritative_confirmation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(make_settings(Path(directory)), error_backoff_seconds=60)
            result = create_service_order(
                document_number="12345678",
                password="password",
                applicant_name="Test",
                priority=1,
                runtime_settings=settings.runtime,
            )
            mark_order_submission_pending(result.order_id, settings=settings.runtime)
            old = (datetime.now() - timedelta(minutes=2)).isoformat(timespec="seconds")
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE order_state SET last_run_at = %s WHERE order_id = %s",
                    (old, result.order_id),
                )

            reconciled = reconcile_pending_submission(
                result.order_id,
                RunReport(status="unavailable", message="No slots", exit_code=0),
                runtime_settings=settings.runtime,
            )

            self.assertFalse(reconciled)
            self.assertTrue(order_reservation_pending(result.order_id, settings=settings.runtime))

    def test_recent_pending_submission_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(make_settings(Path(directory)), error_backoff_seconds=60)
            result = create_service_order(
                document_number="12345678",
                password="password",
                applicant_name="Test",
                priority=1,
                runtime_settings=settings.runtime,
            )
            mark_order_submission_pending(result.order_id, settings=settings.runtime)

            reconciled = reconcile_pending_submission(
                result.order_id,
                RunReport(status="unavailable", message="No slots", exit_code=0),
                runtime_settings=settings.runtime,
            )

            self.assertFalse(reconciled)
            self.assertTrue(order_reservation_pending(result.order_id, settings=settings.runtime))

    def test_exact_programmed_stage_confirms_pending_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="password",
                applicant_name="Test",
                priority=1,
                runtime_settings=settings.runtime,
            )
            attempt_id = self._create_active_attempt(settings, result.order_id)

            reconciled = reconcile_pending_submission(
                result.order_id,
                RunReport(
                    status="completed",
                    message="Programado",
                    exit_code=0,
                    run_id="run-programmed",
                    details={"estado": "Programado", "fecha": "15/09/2026", "hora": "10:30"},
                ),
                runtime_settings=settings.runtime,
            )

            self.assertTrue(reconciled)
            self.assertFalse(order_reservation_pending(result.order_id, settings=settings.runtime))
            with database_connection(settings) as connection:
                attempt = connection.execute(
                    "SELECT status, run_id, resolved_at FROM reservation_attempts "
                    "WHERE attempt_id = %s",
                    (attempt_id,),
                ).fetchone()
            self.assertEqual(attempt["status"], "confirmed")
            self.assertEqual(attempt["run_id"], "run-programmed")
            self.assertIsNotNone(attempt["resolved_at"])

    def test_programmed_stage_with_wrong_slot_stays_unknown_and_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="password",
                applicant_name="Test",
                priority=1,
                runtime_settings=settings.runtime,
            )
            attempt_id = self._create_active_attempt(settings, result.order_id)

            reconciled = reconcile_pending_submission(
                result.order_id,
                RunReport(
                    status="completed",
                    message="Programado en otro horario",
                    exit_code=0,
                    details={"estado": "Programado", "fecha": "15/09/2026", "hora": "11:00"},
                ),
                runtime_settings=settings.runtime,
            )

            self.assertFalse(reconciled)
            self.assertTrue(order_reservation_pending(result.order_id, settings=settings.runtime))
            with database_connection(settings) as connection:
                attempt = connection.execute(
                    "SELECT status, resolved_at FROM reservation_attempts WHERE attempt_id = %s",
                    (attempt_id,),
                ).fetchone()
            self.assertEqual(attempt["status"], "unknown")
            self.assertIsNone(attempt["resolved_at"])

    def test_authoritative_rejection_resolves_intent_pending_and_unknown(self) -> None:
        for active_status in ("intent", "pending", "unknown"):
            with (
                self.subTest(active_status=active_status),
                tempfile.TemporaryDirectory() as directory,
            ):
                settings = make_settings(Path(directory))
                result = create_service_order(
                    document_number="12345678",
                    password="password",
                    applicant_name="Test",
                    priority=1,
                    runtime_settings=settings.runtime,
                )
                attempt_id = self._create_active_attempt(
                    settings,
                    result.order_id,
                    status=active_status,
                )

                reconciled = reconcile_pending_submission(
                    result.order_id,
                    RunReport(status="unavailable", message="No slots", exit_code=0),
                    runtime_settings=settings.runtime,
                )

                self.assertTrue(reconciled)
                self.assertFalse(
                    order_reservation_pending(result.order_id, settings=settings.runtime)
                )
                with database_connection(settings) as connection:
                    attempt = connection.execute(
                        "SELECT status, resolved_at FROM reservation_attempts "
                        "WHERE attempt_id = %s",
                        (attempt_id,),
                    ).fetchone()
                self.assertEqual(attempt["status"], "rejected")
                self.assertIsNotNone(attempt["resolved_at"])


if __name__ == "__main__":
    unittest.main()
