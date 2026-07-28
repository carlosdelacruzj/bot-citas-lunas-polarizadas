from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from appointment_bot.db.orders import (
    claim_service_order,
    create_service_order,
    mark_order_submission_pending,
    order_reservation_pending,
    set_order_paused,
)
from appointment_bot.domain import RunReport
from appointment_bot.services.order_transitions import (
    order_can_submit,
    reconcile_pending_submission,
)
from tests.helpers import database_connection, make_settings


class OrderTransitionTests(unittest.TestCase):
    def test_paused_order_cannot_submit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="password",
                applicant_name="Test",
                priority=1,
                require_preflight=False,
                settings=settings,
            )
            owner = "test-worker"
            self.assertTrue(
                claim_service_order(
                    result.order_id,
                    owner_token=owner,
                    lease_seconds=60,
                    settings=settings,
                )
            )

            self.assertTrue(order_can_submit(result.order_id, owner, settings))

            set_order_paused(result.order_id, True, settings=settings)

            self.assertFalse(order_can_submit(result.order_id, owner, settings))

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
                settings=settings,
            )
            mark_order_submission_pending(result.order_id, settings=settings)
            old = (datetime.now() - timedelta(minutes=2)).isoformat(timespec="seconds")
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE order_state SET last_run_at = %s WHERE order_id = %s",
                    (old, result.order_id),
                )

            reconciled = reconcile_pending_submission(
                result.order_id,
                RunReport(status="unavailable", message="No slots", exit_code=0),
                settings,
            )

            self.assertFalse(reconciled)
            self.assertTrue(order_reservation_pending(result.order_id, settings=settings))

    def test_recent_pending_submission_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(make_settings(Path(directory)), error_backoff_seconds=60)
            result = create_service_order(
                document_number="12345678",
                password="password",
                applicant_name="Test",
                priority=1,
                settings=settings,
            )
            mark_order_submission_pending(result.order_id, settings=settings)

            reconciled = reconcile_pending_submission(
                result.order_id,
                RunReport(status="unavailable", message="No slots", exit_code=0),
                settings,
            )

            self.assertFalse(reconciled)
            self.assertTrue(order_reservation_pending(result.order_id, settings=settings))


if __name__ == "__main__":
    unittest.main()
