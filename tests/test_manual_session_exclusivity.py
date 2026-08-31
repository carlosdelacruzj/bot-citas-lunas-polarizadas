from __future__ import annotations

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock, patch

from appointment_bot.core.models import ServiceOrderRuntime
from appointment_bot.db.browser_ownership import (
    BrowserOwnershipConflict,
    acquire_browser_ownership,
)
from appointment_bot.db.orders import (
    claim_service_order,
    create_service_order,
    release_service_order_claim,
)
from appointment_bot.db.reservations import create_reservation_attempt
from appointment_bot.manual_session import session as manual_sessions
from appointment_bot.manual_session.session import ManualSessionHandle
from appointment_bot.services.api.manual_session_routes import open_manual_session_payload
from tests.helpers import make_settings


def _create_order(settings, expediente: str):
    return create_service_order(
        document_number="12345678",
        password="secret",
        program_expediente=expediente,
        require_preflight=False,
        settings=settings,
    )


class ManualSessionExclusivityTests(unittest.TestCase):
    def tearDown(self) -> None:
        with manual_sessions._ACTIVE_SESSION_LOCK:
            manual_sessions._ACTIVE_SESSIONS.clear()

    def test_concurrent_account_admission_allows_exactly_one_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            first = _create_order(settings, "EXP-A")
            second = _create_order(settings, "EXP-B")
            barrier = threading.Barrier(2)

            def acquire(order_id: str, owner: str) -> tuple[str, str, str]:
                barrier.wait()
                try:
                    acquire_browser_ownership(
                        order_id,
                        owner_token=owner,
                        purpose="manual",
                        lease_seconds=60,
                        settings=settings,
                    )
                except BrowserOwnershipConflict as exc:
                    return "conflict", exc.code, order_id
                return "acquired", owner, order_id

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [
                    executor.submit(
                        acquire,
                        first.order_id,
                        "manual-session-first",
                    ),
                    executor.submit(
                        acquire,
                        second.order_id,
                        "manual-session-second",
                    ),
                ]
                outcomes = [future.result(timeout=10) for future in results]

            acquired = [item for item in outcomes if item[0] == "acquired"]
            conflicts = [item for item in outcomes if item[0] == "conflict"]
            self.assertEqual(len(acquired), 1)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0][1], "manual_session_exists")
            release_service_order_claim(
                acquired[0][2],
                owner_token=acquired[0][1],
                settings=settings,
            )

    def test_manual_owner_blocks_worker_on_another_order_of_same_account(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            first = _create_order(settings, "EXP-A")
            second = _create_order(settings, "EXP-B")
            acquire_browser_ownership(
                first.order_id,
                owner_token="manual-session-owner",
                purpose="manual",
                lease_seconds=60,
                settings=settings,
            )

            claimed = claim_service_order(
                second.order_id,
                owner_token="worker-owner",
                lease_seconds=60,
                settings=settings,
            )

            self.assertFalse(claimed)

    def test_preflight_browser_owner_is_reported_as_browser_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            first = _create_order(settings, "EXP-A")
            second = _create_order(settings, "EXP-B")
            acquire_browser_ownership(
                first.order_id,
                owner_token="preflight-owner",
                purpose="preflight",
                lease_seconds=60,
                settings=settings,
            )

            with self.assertRaises(BrowserOwnershipConflict) as context:
                acquire_browser_ownership(
                    second.order_id,
                    owner_token="manual-session-owner",
                    purpose="manual",
                    lease_seconds=60,
                    settings=settings,
                )

            self.assertEqual(context.exception.code, "browser_job_active")

    def test_worker_lease_active_attempt_and_preflight_are_rejected(self) -> None:
        cases = ("worker", "attempt", "preflight")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                settings = make_settings(Path(directory))
                order = create_service_order(
                    document_number="12345678",
                    password="secret",
                    require_preflight=case == "preflight",
                    settings=settings,
                )
                if case == "worker":
                    self.assertTrue(
                        claim_service_order(
                            order.order_id,
                            owner_token="worker-owner",
                            lease_seconds=60,
                            settings=settings,
                        )
                    )
                    expected = "service_order_lease_active"
                elif case == "attempt":
                    create_reservation_attempt(
                        "attempt-test",
                        order.order_id,
                        details=None,
                        settings=settings,
                    )
                    expected = "active_reservation_attempt"
                else:
                    expected = "preflight_in_progress"

                with self.assertRaises(BrowserOwnershipConflict) as context:
                    acquire_browser_ownership(
                        order.order_id,
                        owner_token="manual-session-owner",
                        purpose="manual",
                        lease_seconds=60,
                        settings=settings,
                    )

                self.assertEqual(context.exception.code, expected)

    def test_manual_session_route_maps_every_ownership_conflict_to_409(self) -> None:
        order = ServiceOrderRuntime(
            order_id="order-test",
            name="Test",
            username="12345678",
            document_type="dni",
            password="secret",
            priority=0,
            status="ready",
            created_at="2026-08-31T10:00:00+00:00",
            updated_at="2026-08-31T10:00:00+00:00",
        )
        conflict_codes = (
            "service_order_lease_active",
            "active_reservation_attempt",
            "preflight_in_progress",
            "browser_job_active",
            "manual_session_exists",
        )
        for code in conflict_codes:
            with (
                self.subTest(code=code),
                patch.dict("os.environ", {"MANUAL_SESSION_ENABLED": "true"}),
                patch(
                    "appointment_bot.services.api.manual_session_routes.load_settings",
                    return_value=Mock(),
                ),
                patch(
                    "appointment_bot.services.api.manual_session_routes."
                    "get_service_order_runtime",
                    return_value=order,
                ),
                patch(
                    "appointment_bot.services.api.manual_session_routes."
                    "open_manual_session_for_order",
                    side_effect=BrowserOwnershipConflict(code, "conflict"),
                ),
            ):
                status, payload = open_manual_session_payload(
                    {"order_id": order.order_id, "mode": "appointment"},
                    server_host="127.0.0.1",
                    client_host="127.0.0.1",
                )

            self.assertEqual(status, HTTPStatus.CONFLICT)
            self.assertEqual(payload["status"], code)

    def test_close_timeout_keeps_session_in_inventory_and_restart_barrier(self) -> None:
        lease = Mock()
        lease.lost = False
        handle = ManualSessionHandle(
            session_id="manual-session-test",
            order_id="order-test",
            username="12***8",
            mode="appointment",
            order_status="ready",
            status="active",
            status_message=None,
            started_at="2026-08-31T10:00:00+00:00",
            updated_at="2026-08-31T10:00:00+00:00",
            close_requested=threading.Event(),
            browser_lease=lease,
            thread=Mock(),
            diagnostic_report_path=None,
            diagnostic_event_count=0,
            diagnostic_submission_seen=False,
            diagnostic_honeypot_blocked=False,
        )
        with manual_sessions._ACTIVE_SESSION_LOCK:
            manual_sessions._ACTIVE_SESSIONS[handle.session_id] = handle

        with patch("appointment_bot.manual_session.session.threading.Timer") as timer:
            self.assertTrue(manual_sessions.close_manual_session(handle.session_id))
        timer.return_value.start.assert_called_once()
        self.assertEqual(handle.status, "closing")

        manual_sessions._expire_closing_session(handle.session_id, handle)

        self.assertEqual(handle.status, "close_timeout")
        self.assertIn(handle.session_id, manual_sessions._ACTIVE_SESSIONS)
        self.assertEqual(
            manual_sessions.blocking_manual_sessions()[0]["status"],
            "close_timeout",
        )


if __name__ == "__main__":
    unittest.main()
