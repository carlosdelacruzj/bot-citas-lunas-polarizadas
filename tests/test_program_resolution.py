from __future__ import annotations

import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from appointment_bot.db.order_credentials import create_service_order
from appointment_bot.db.order_preflight import (
    mark_order_preflight_failed,
    mark_order_preflight_pending,
)
from appointment_bot.db.orders import list_service_order_summaries
from appointment_bot.db.program_resolution import (
    ProgramResolutionConflict,
    get_order_program_listing,
    record_order_program_listing,
    resolve_service_order_programs,
    split_service_order_programs,
)
from appointment_bot.services.api.operator_inbox_routes import _order_task
from appointment_bot.services.api.service_order_routes import (
    resolve_service_order_programs_payload,
    split_service_order_programs_payload,
)
from appointment_bot.services.order_preflight import validate_order_preflight
from tests.helpers import database_connection, make_settings


def _row(expediente: str, plate: str, status: str) -> dict[str, object]:
    return {
        "action_index": 0,
        "expediente": expediente,
        "placa": plate,
        "status": status,
    }


class ProgramPreflightTests(unittest.TestCase):
    def _validate(self, settings, order_id: str, rows: list[dict[str, object]]):
        mark_order_preflight_pending(order_id, settings=settings)
        with (
            patch(
                "appointment_bot.services.order_preflight.open_page",
                return_value=nullcontext(object()),
            ),
            patch("appointment_bot.services.order_preflight.login"),
            patch(
                "appointment_bot.services.order_preflight._read_portal_applicant_name",
                return_value="Cliente Prueba",
            ),
            patch(
                "appointment_bot.services.order_preflight.read_program_action_rows",
                return_value=rows,
            ),
            patch("appointment_bot.services.order_preflight._queue_notice") as notice,
            patch(
                "appointment_bot.services.order_preflight.send_telegram_message"
            ) as internal_signal,
        ):
            result = validate_order_preflight(order_id, settings=settings)
        return result, notice, internal_signal

    def test_cancelled_plus_one_pending_validates_normally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order = create_service_order(
                document_number="45111111", password="secret", settings=settings
            )
            result, notice, _ = self._validate(
                settings,
                order.order_id,
                [_row("EXP-C", "ABC111", "CANCELADO"), _row("EXP-P", "ABC111", "PENDIENTE")],
            )
            summary = list_service_order_summaries(settings)[0]

            self.assertEqual(result["status"], "validated")
            self.assertEqual(result["pending_count"], 1)
            self.assertEqual(summary.status, "ready")
            notice.assert_called_once()

    def test_multiple_pending_blocks_without_customer_notice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order = create_service_order(
                document_number="45222222", password="secret", settings=settings
            )
            result, notice, internal_signal = self._validate(
                settings,
                order.order_id,
                [_row("EXP-1", "AAA111", "PENDIENTE"), _row("EXP-2", "BBB222", "PENDIENTE")],
            )
            summary = list_service_order_summaries(settings)[0]
            with database_connection(settings) as connection:
                jobs = connection.execute(
                    "SELECT count(*) AS count FROM whatsapp_automation_jobs"
                ).fetchone()["count"]

            self.assertEqual(result["error_type"], "multiple_pending_resolution_required")
            self.assertEqual(summary.status, "paused")
            self.assertEqual(summary.preflight_status, "failed")
            self.assertEqual(len(summary.preflight_details["pending_programs"]), 2)
            self.assertTrue(summary.preflight_details["listing_signature"])
            notice.assert_not_called()
            internal_signal.assert_called_once()
            internal_message = internal_signal.call_args.args[1]
            self.assertIn("elegir uno, todos o mantener la orden pausada", internal_message)
            self.assertIn("Tramites PENDIENTE detectados: 2", internal_message)
            self.assertNotIn("error tecnico", internal_message.casefold())
            self.assertEqual(jobs, 0)

    def test_target_must_match_one_pending_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order = create_service_order(
                document_number="45333333",
                password="secret",
                program_plate="DUP111",
                settings=settings,
            )
            result, notice, _ = self._validate(
                settings,
                order.order_id,
                [_row("EXP-1", "DUP111", "PENDIENTE"), _row("EXP-2", "DUP111", "PENDIENTE")],
            )
            self.assertEqual(result["error_type"], "program_target_not_unique")
            notice.assert_not_called()

    def test_target_matching_one_pending_row_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order = create_service_order(
                document_number="45333334",
                password="secret",
                program_expediente="EXP-2",
                settings=settings,
            )
            result, notice, _ = self._validate(
                settings,
                order.order_id,
                [_row("EXP-1", "AAA111", "PENDIENTE"), _row("EXP-2", "BBB222", "PENDIENTE")],
            )
            self.assertEqual(result["status"], "validated")
            self.assertEqual(result["programs"][0]["expediente"], "EXP-2")
            notice.assert_called_once()

    def test_target_plate_ignores_non_alphanumeric_punctuation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order = create_service_order(
                document_number="45333335",
                password="secret",
                program_plate="ABC-123",
                settings=settings,
            )
            result, notice, _ = self._validate(
                settings,
                order.order_id,
                [_row("EXP-1", "ABC 123", "PENDIENTE")],
            )
            self.assertEqual(result["status"], "validated")
            notice.assert_called_once()


class ProgramResolutionTests(unittest.TestCase):
    def _order_with_listing(self, settings, document: str):
        order = create_service_order(
            document_number=document, password="secret", settings=settings
        )
        record_order_program_listing(
            order.order_id,
            {
                "program_count": 3,
                "pending_count": 2,
                "rows": [
                    _row("EXP-1", "AAA111", "PENDIENTE"),
                    _row("EXP-X", "OLD000", "CANCELADO"),
                    _row("EXP-2", "BBB222", "PENDIENTE"),
                ],
                "source": "test",
            },
            settings=settings,
        )
        mark_order_preflight_failed(
            order.order_id,
            "La cuenta tiene varios tramites PENDIENTE.",
            details={"error_type": "multiple_pending_resolution_required"},
            settings=settings,
        )
        return order, get_order_program_listing(order.order_id, settings=settings)

    def test_operator_inbox_routes_multiple_pending_to_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            self._order_with_listing(settings, "45444442")
            task = _order_task(list_service_order_summaries(settings)[0])

            self.assertIsNotNone(task)
            self.assertEqual(task["action"], "resolve_programs")
            self.assertEqual(task["kind"], "program_resolution")

    def test_listing_signature_ignores_volatile_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, first = self._order_with_listing(settings, "45444443")
            changed = record_order_program_listing(
                order.order_id,
                {
                    "program_count": 999,
                    "pending_count": 999,
                    "decision": "different_runtime_decision",
                    "rows": first["details"]["rows"],
                    "source": "another_runtime_source",
                },
                settings=settings,
            )
            same_rows = get_order_program_listing(order.order_id, settings=settings)
            changed_rows = [dict(row) for row in first["details"]["rows"]]
            changed_rows[0]["status"] = "ATENDIDO"
            row_changed = record_order_program_listing(
                order.order_id,
                {"rows": changed_rows, "source": "another_runtime_source"},
                settings=settings,
            )
            final = get_order_program_listing(order.order_id, settings=settings)

            self.assertFalse(changed)
            self.assertEqual(same_rows["signature"], first["signature"])
            self.assertEqual(same_rows["revision"], first["revision"])
            self.assertTrue(row_changed)
            self.assertNotEqual(final["signature"], first["signature"])
            self.assertEqual(final["revision"], first["revision"] + 1)

    def test_stale_listing_returns_stable_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, _ = self._order_with_listing(settings, "45444444")
            with patch.dict(
                "os.environ", {"APPOINTMENT_DATABASE_URL": settings.database_url}, clear=False
            ):
                status, payload = resolve_service_order_programs_payload(
                    order.order_id,
                    {
                        "resolution": "one",
                        "listing_signature": "stale",
                        "program_expediente": "EXP-1",
                        "communication_decision": "keep_without_send",
                    },
                    requested_by="api-test",
                )
            self.assertEqual(int(status), 409)
            self.assertEqual(payload["status"], "program_listing_stale")

    def test_one_requires_unique_pending_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45555555")
            result = resolve_service_order_programs(
                order.order_id,
                resolution="one",
                listing_signature=listing["signature"],
                communication_decision="keep_without_send",
                actor="api-test",
                program_expediente="EXP-2",
                settings=settings,
            )
            summary = list_service_order_summaries(settings)[0]
            self.assertEqual(result["selected_program"]["expediente"], "EXP-2")
            self.assertEqual(summary.program_expediente, "EXP-2")
            self.assertEqual(summary.status, "paused")

    def test_resolution_api_normalizes_untrusted_actor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45555556")
            with patch.dict(
                "os.environ", {"APPOINTMENT_DATABASE_URL": settings.database_url}, clear=False
            ):
                status, payload = resolve_service_order_programs_payload(
                    order.order_id,
                    {
                        "resolution": "one",
                        "listing_signature": listing["signature"],
                        "program_expediente": "EXP-1",
                        "communication_decision": "keep_without_send",
                    },
                    requested_by="raw actor<script>",
                )
            persisted = get_order_program_listing(order.order_id, settings=settings)

            self.assertEqual(int(status), 200)
            self.assertEqual(payload["status"], "applied")
            self.assertEqual(persisted["resolution"]["actor"], "admin_api")

    def test_all_is_atomic_idempotent_and_creates_no_whatsapp_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45666666")
            first = resolve_service_order_programs(
                order.order_id,
                resolution="all",
                listing_signature=listing["signature"],
                communication_decision="preview_single_confirmation",
                actor="api-test",
                confirm_same_commercial_terms=True,
                settings=settings,
            )
            second = resolve_service_order_programs(
                order.order_id,
                resolution="all",
                listing_signature=listing["signature"],
                communication_decision="preview_single_confirmation",
                actor="api-test",
                confirm_same_commercial_terms=True,
                settings=settings,
            )
            with database_connection(settings) as connection:
                children = connection.execute(
                    "SELECT order_id FROM service_orders WHERE parent_order_id = %s",
                    (order.order_id,),
                ).fetchall()
                jobs = connection.execute(
                    "SELECT count(*) AS count FROM whatsapp_automation_jobs"
                ).fetchone()["count"]
            summaries = {item.order_id: item for item in list_service_order_summaries(settings)}

            self.assertEqual(first["status"], "applied")
            self.assertEqual(second["status"], "already_applied")
            self.assertEqual(second["audit_id"], first["audit_id"])
            self.assertEqual(len(children), 2)
            self.assertEqual(summaries[order.order_id].status, "archived")
            self.assertTrue(first["parent_archived"])
            self.assertIn("aun no fue enviado", first["communication_preview"])
            self.assertEqual(jobs, 0)

    def test_different_resolution_cannot_replace_applied_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45666667")
            resolve_service_order_programs(
                order.order_id,
                resolution="all",
                listing_signature=listing["signature"],
                communication_decision="keep_without_send",
                actor="api-test",
                confirm_same_commercial_terms=True,
                settings=settings,
            )

            with self.assertRaises(ProgramResolutionConflict) as context:
                resolve_service_order_programs(
                    order.order_id,
                    resolution="pause",
                    listing_signature=listing["signature"],
                    communication_decision="keep_without_send",
                    actor="api-test",
                    settings=settings,
                )
            summaries = {item.order_id: item for item in list_service_order_summaries(settings)}

            self.assertEqual(context.exception.code, "program_resolution_already_applied")
            self.assertEqual(summaries[order.order_id].status, "archived")

    def test_all_rolls_back_if_second_child_creation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45777777")
            real_create = create_service_order
            calls = 0

            def fail_second_child(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("synthetic second-child failure")
                return real_create(*args, **kwargs)

            with (
                patch(
                    "appointment_bot.db.program_resolution.create_service_order",
                    side_effect=fail_second_child,
                ),
                self.assertRaises(RuntimeError),
            ):
                resolve_service_order_programs(
                    order.order_id,
                    resolution="all",
                    listing_signature=listing["signature"],
                    communication_decision="keep_without_send",
                    actor="api-test",
                    confirm_same_commercial_terms=True,
                    settings=settings,
                )
            with database_connection(settings) as connection:
                count = connection.execute(
                    "SELECT count(*) AS count FROM service_orders WHERE parent_order_id = %s",
                    (order.order_id,),
                ).fetchone()["count"]
            self.assertEqual(count, 0)

    def test_all_fails_closed_for_financial_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45888888")
            with database_connection(settings) as connection:
                connection.execute(
                    """
                    INSERT INTO payments (
                        payment_id, order_id, status, amount_agreed, amount_paid,
                        currency, created_at, updated_at
                    ) VALUES ('payment-test', %s, 'pending', 50, 10, 'PEN', NOW(), NOW())
                    """,
                    (order.order_id,),
                )
            with self.assertRaises(ProgramResolutionConflict) as context:
                resolve_service_order_programs(
                    order.order_id,
                    resolution="all",
                    listing_signature=listing["signature"],
                    communication_decision="keep_without_send",
                    actor="api-test",
                    confirm_same_commercial_terms=True,
                    settings=settings,
                )
            self.assertEqual(
                context.exception.code,
                "program_resolution_financial_allocation_required",
            )

    def test_all_rejects_integral_child_even_with_charge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45888889")
            child_specs = [
                {
                    "program_expediente": expediente,
                    "program_plate": plate,
                    "charge_required": True,
                    "service_type": "standard",
                    "service_package": "integral",
                    "reservation_price": "160.00",
                    "minimum_reservation_date": None,
                    "maximum_reservation_date": None,
                    "allowed_weekdays": [],
                    "excluded_date_ranges": [],
                }
                for expediente, plate in (("EXP-1", "AAA111"), ("EXP-2", "BBB222"))
            ]
            with self.assertRaises(ProgramResolutionConflict) as context:
                resolve_service_order_programs(
                    order.order_id,
                    resolution="all",
                    listing_signature=listing["signature"],
                    communication_decision="keep_without_send",
                    actor="api-test",
                    children=child_specs,
                    settings=settings,
                )
            self.assertEqual(context.exception.code, "program_integral_split_unsupported")

    def test_resolution_requires_expected_preflight_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45888890")
            mark_order_preflight_pending(order.order_id, settings=settings)

            with self.assertRaises(ProgramResolutionConflict) as context:
                resolve_service_order_programs(
                    order.order_id,
                    resolution="pause",
                    listing_signature=listing["signature"],
                    communication_decision="keep_without_send",
                    actor="api-test",
                    settings=settings,
                )

            self.assertEqual(context.exception.code, "program_resolution_preflight_conflict")

    def test_resolution_requires_paused_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45888893")
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE service_orders SET status = 'ready' WHERE order_id = %s",
                    (order.order_id,),
                )

            with self.assertRaises(ProgramResolutionConflict) as context:
                resolve_service_order_programs(
                    order.order_id,
                    resolution="pause",
                    listing_signature=listing["signature"],
                    communication_decision="keep_without_send",
                    actor="api-test",
                    settings=settings,
                )

            self.assertEqual(context.exception.code, "program_resolution_invalid_state")

    def test_resolution_blocks_active_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45888891")
            with database_connection(settings) as connection:
                connection.execute(
                    """
                    UPDATE service_orders
                    SET lease_owner = 'worker-test',
                        lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '5 minutes'
                    WHERE order_id = %s
                    """,
                    (order.order_id,),
                )

            with self.assertRaises(ProgramResolutionConflict) as context:
                resolve_service_order_programs(
                    order.order_id,
                    resolution="pause",
                    listing_signature=listing["signature"],
                    communication_decision="keep_without_send",
                    actor="api-test",
                    settings=settings,
                )

            self.assertEqual(context.exception.code, "program_resolution_active_lease")

    def test_resolution_blocks_active_reservation_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            order, listing = self._order_with_listing(settings, "45888892")
            with database_connection(settings) as connection:
                connection.execute(
                    """
                    INSERT INTO reservation_attempts (
                        attempt_id, order_id, idempotency_key, status,
                        created_at, updated_at
                    ) VALUES ('attempt-program-resolution', %s, 'program-resolution-key',
                              'unknown', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (order.order_id,),
                )

            with self.assertRaises(ProgramResolutionConflict) as context:
                resolve_service_order_programs(
                    order.order_id,
                    resolution="pause",
                    listing_signature=listing["signature"],
                    communication_decision="keep_without_send",
                    actor="api-test",
                    settings=settings,
                )

            self.assertEqual(context.exception.code, "program_resolution_active_attempt")

    def test_legacy_split_returns_stable_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            with patch.dict(
                "os.environ", {"APPOINTMENT_DATABASE_URL": settings.database_url}, clear=False
            ):
                status, payload = split_service_order_programs_payload("legacy-order", {})

            self.assertEqual(int(status), 409)
            self.assertEqual(payload["status"], "explicit_program_resolution_required")
            with self.assertRaises(ProgramResolutionConflict) as context:
                split_service_order_programs("legacy-order", settings=settings)
            self.assertEqual(
                context.exception.code,
                "explicit_program_resolution_required",
            )


if __name__ == "__main__":
    unittest.main()
