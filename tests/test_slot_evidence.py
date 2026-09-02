from __future__ import annotations

import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from appointment_bot.core.models import AvailabilityResult
from appointment_bot.reports.run_reporting import record_run_history, report_from_result
from appointment_bot.reservation_engine import monitor
from appointment_bot.reservation_engine.ports import ReservationEnginePorts
from appointment_bot.reservation_engine.reservation_flow import (
    capture_blocked_captcha_evidence,
)
from appointment_bot.reservation_engine.slot_evidence import (
    CanonicalSlotCaptureError,
    capture_canonical_selected_slot,
)
from appointment_bot.services.notifier import notify_result
from appointment_bot.services.unique_slot_watermark import (
    LAYOUT_VERSION,
    ensure_unique_slot_watermark,
)
from appointment_bot.utils.screenshots import archive_unique_slot_capture
from tests.helpers import make_settings


def _available_result() -> AvailabilityResult:
    return AvailabilityResult(
        status="available",
        message="Cupo seleccionado.",
        details={"sede": "Lima", "fecha": "01/09/2026", "hora": "10:30"},
    )


def _engine_ports() -> ReservationEnginePorts:
    return ReservationEnginePorts(
        runs=Mock(),
        alerts=Mock(),
        captcha=Mock(),
        opportunities=Mock(),
    )


class SlotEvidenceTests(unittest.TestCase):
    def test_archive_uses_slot_index_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            source = Path(directory) / "selected.png"
            source.write_bytes(b"slot")
            details = {"fecha": "01/09/2026", "hora": "10:30"}

            archived = archive_unique_slot_capture(settings, details, source)
            repeated = archive_unique_slot_capture(settings, details, source)

            self.assertIsNotNone(archived)
            self.assertEqual(archived, repeated)
            self.assertEqual(archived.name, "01-09-2026_10-30.png")
            self.assertEqual(archived.parent.name, "cupos-unicos")
            self.assertEqual(archived.read_bytes(), b"slot")

    def test_run_history_queues_watermark_after_archiving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            archived = Path(directory) / "cupos-unicos" / "01-09-2026_10-30.png"
            report = replace(
                report_from_result(_available_result()),
                run_id="run-1",
                started_at="2026-09-02T10:00:00+00:00",
                finished_at="2026-09-02T10:00:01+00:00",
                duration_seconds=1.0,
            )

            with (
                patch(
                    "appointment_bot.reports.run_reporting."
                    "archive_unique_slot_screenshots",
                    return_value=[archived],
                ),
                patch(
                    "appointment_bot.reports.run_reporting.queue_unique_slot_watermark"
                ) as queue_watermark,
                patch("appointment_bot.reports.run_reporting.record_run_outcome"),
            ):
                record_run_history(settings, report)

            queue_watermark.assert_called_once_with(settings, archived)

    def test_archived_slot_produces_a_verified_watermarked_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            source = Path(directory) / "selected.png"
            Image.new("RGB", (900, 600), "white").save(source)

            archived = archive_unique_slot_capture(
                settings,
                {"fecha": "01/09/2026", "hora": "10:30"},
                source,
            )

            branded = ensure_unique_slot_watermark(
                settings,
                archived,
                public_whatsapp="925761698",
            )

            self.assertEqual(branded.name, archived.name)
            self.assertEqual(branded.parent.name, "cupos-unicos-marcados")
            with Image.open(branded) as image:
                self.assertEqual(image.info["watermark_layout"], LAYOUT_VERSION)
                image.verify()

    def test_capture_archives_after_stable_modal_and_records_phase(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            source = Path(directory) / "cupo-selected.png"
            archived = Path(directory) / "cupos-unicos" / "20260901-1030.png"
            source.write_bytes(b"slot")
            archived.parent.mkdir()
            archived.write_bytes(b"slot")
            calls: list[str] = []

            with (
                patch(
                    "appointment_bot.reservation_engine.slot_evidence."
                    "save_available_appointment_snapshot",
                    side_effect=lambda *_args: calls.append("capture") or source,
                ),
                patch(
                    "appointment_bot.reservation_engine.slot_evidence."
                    "archive_unique_slot_capture",
                    side_effect=lambda *_args: calls.append("archive") or archived,
                ),
            ):
                result, source_path, archived_path = capture_canonical_selected_slot(
                    object(),
                    settings,
                    _available_result(),
                    phase="initial_selection",
                )

            self.assertEqual(calls, ["capture", "archive"])
            self.assertEqual(source_path, source)
            self.assertEqual(archived_path, archived)
            capture = result.details["canonical_slot_capture"]
            self.assertTrue(capture["captured_before_captcha"])
            self.assertEqual(capture["phase"], "initial_selection")
            self.assertEqual(result.details["_unique_slot_evidence"][0]["hora"], "10:30")

    def test_missing_slot_identity_fails_before_screenshot(self) -> None:
        settings = make_settings(Path("unused"))
        with (
            patch(
                "appointment_bot.reservation_engine.slot_evidence."
                "save_available_appointment_snapshot"
            ) as save,
            self.assertRaises(CanonicalSlotCaptureError),
        ):
            capture_canonical_selected_slot(
                object(),
                settings,
                AvailabilityResult(
                    status="available",
                    message="Sin hora.",
                    details={"fecha": "01/09/2026"},
                ),
                phase="initial_selection",
            )
        save.assert_not_called()

    def test_available_capture_failure_stops_before_captcha_and_submit(self) -> None:
        settings = make_settings(Path("unused"))
        submit_intent = Mock()
        submit_started = Mock()
        with (
            patch(
                "appointment_bot.reservation_engine.monitor.select_available_appointment",
                return_value=_available_result(),
            ),
            patch(
                "appointment_bot.reservation_engine.monitor."
                "capture_canonical_selected_slot",
                side_effect=CanonicalSlotCaptureError("disk unavailable"),
            ),
            patch(
                "appointment_bot.reservation_engine.monitor.complete_available_reservation"
            ) as complete,
        ):
            outcome = monitor._try_reservation_from_availability(
                object(),
                settings,
                _available_result(),
                1,
                time.monotonic(),
                time.monotonic(),
                None,
                [],
                None,
                None,
                None,
                None,
                None,
                None,
                submit_intent,
                submit_started,
                None,
                None,
                None,
                None,
                "run-test",
                "order-test",
                _engine_ports(),
            )

        self.assertEqual(outcome.completed_result[0].status, "error")
        self.assertTrue(
            outcome.completed_result[0].details["canonical_slot_capture_failed"]
        )
        complete.assert_not_called()
        submit_intent.assert_not_called()
        submit_started.assert_not_called()

    def test_blocked_slot_never_starts_a_reservation_attempt(self) -> None:
        settings = make_settings(Path("unused"))
        blocked = AvailabilityResult(
            status="partial",
            message="Bloqueado por regla.",
            details={
                "fecha": "01/09/2026",
                "hora": "10:30",
                "blocked_by_order_rule": True,
                "blocked_selected_for_evidence": True,
            },
        )
        slot = Path("selected-slot.png")
        captured = replace(
            blocked,
            details={
                **blocked.details,
                "submission_outcome": "blocked_by_order_rule",
            },
        )
        submit_intent = Mock()
        submit_started = Mock()

        with (
            patch.object(monitor, "select_available_appointment", return_value=blocked),
            patch.object(
                monitor,
                "capture_canonical_selected_slot",
                return_value=(blocked, slot, slot),
            ) as capture_slot,
            patch.object(
                monitor,
                "capture_blocked_captcha_evidence",
                return_value=(captured, slot, [slot]),
            ) as capture_captcha,
            patch.object(monitor, "complete_available_reservation") as complete,
        ):
            outcome = monitor._try_reservation_from_availability(
                page=object(),
                settings=settings,
                result=_available_result(),
                attempt=1,
                session_started=time.monotonic(),
                check_started=time.monotonic(),
                screenshot_path=None,
                screenshot_paths=[],
                reservation_timing=None,
                cancel_event=None,
                on_check=None,
                is_allowed_appointment=None,
                can_submit=None,
                can_solve_captcha=None,
                on_submission_intent=submit_intent,
                on_submission_started=submit_started,
                on_submission_resolved=None,
                expected_person_name=None,
                program_expediente=None,
                program_plate=None,
                run_id="run-test",
                order_id="order-test",
                ports=_engine_ports(),
            )

        self.assertEqual(outcome.completed_result[0].status, "partial")
        self.assertFalse(
            report_from_result(outcome.completed_result[0]).reservation_attempted
        )
        self.assertEqual(
            capture_slot.call_args.kwargs["phase"], "blocked_by_order_rule"
        )
        capture_captcha.assert_called_once()
        complete.assert_not_called()
        submit_intent.assert_not_called()
        submit_started.assert_not_called()

    def test_blocked_evidence_keeps_slot_before_captcha_and_no_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            slot = Path(directory) / "cupo-selected.png"
            captcha = Path(directory) / "captcha.png"
            slot.write_bytes(b"slot")
            captcha.write_bytes(b"captcha")
            result = AvailabilityResult(
                status="partial",
                message="Bloqueado por regla.",
                details={
                    "fecha": "01/09/2026",
                    "hora": "10:30",
                    "blocked_by_order_rule": True,
                    "blocked_selected_for_evidence": True,
                },
            )

            def capture_only(*_args, **kwargs):
                kwargs["captcha_audit"]["captcha_image_path"] = str(captcha)

            with patch(
                "appointment_bot.reservation_engine.reservation_flow."
                "solve_reservation_captcha_and_click_reserve",
                side_effect=capture_only,
            ):
                captured, primary, paths = capture_blocked_captcha_evidence(
                    object(), settings, result, slot
                )

            report = report_from_result(captured, screenshot_path=primary, screenshot_paths=paths)
            self.assertEqual(primary, slot)
            self.assertEqual(paths, [slot, captcha])
            self.assertEqual(captured.details["submission_outcome"], "blocked_by_order_rule")
            self.assertFalse(report.reservation_attempted)

    def test_blocked_notification_sends_slot_before_secondary_captcha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            slot = Path(directory) / "cupo-selected.png"
            captcha = Path(directory) / "captcha.png"
            slot.write_bytes(b"slot")
            captcha.write_bytes(b"captcha")
            result = AvailabilityResult(
                status="partial",
                message="Bloqueado por regla.",
                details={
                    "fecha": "01/09/2026",
                    "hora": "10:30",
                    "blocked_by_order_rule": True,
                    "submission_outcome": "blocked_by_order_rule",
                },
            )

            with patch(
                "appointment_bot.services.notifier.send_telegram_photo",
                return_value=True,
            ) as send_photo:
                delivered = notify_result(
                    result,
                    settings,
                    screenshot_path=slot,
                    screenshot_paths=[slot, captcha],
                )

            self.assertTrue(delivered)
            self.assertEqual(send_photo.call_count, 2)
            self.assertEqual(send_photo.call_args_list[0].args[1], slot)
            self.assertEqual(send_photo.call_args_list[1].args[1], captcha)

    def test_reobservation_archives_recovered_slot_before_second_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(
                make_settings(Path(directory)),
                slot_lost_reobservation_attempts=1,
                slot_lost_reobservation_seconds=5,
            )
            original_slot = Path(directory) / "cupo-original.png"
            recovered_slot = Path(directory) / "cupo-recovered.png"
            original_slot.write_bytes(b"original")
            recovered_slot.write_bytes(b"recovered")
            original = (
                AvailabilityResult(
                    status="unavailable",
                    message="Cupo perdido.",
                    details={
                        "fecha": "01/09/2026",
                        "hora": "10:30",
                        "submission_outcome": "slot_lost",
                    },
                ),
                original_slot,
                [original_slot],
            )
            recovered = AvailabilityResult(
                status="available",
                message="Cupo recuperado.",
                details={"fecha": "02/09/2026", "hora": "11:00"},
            )
            registered = AvailabilityResult(
                status="registered",
                message="Reservado.",
                details={
                    "fecha": "02/09/2026",
                    "hora": "11:00",
                    "submission_outcome": "confirmed",
                },
            )
            calls: list[str] = []

            with (
                patch.object(monitor, "_record_reobservation_event", return_value=True),
                patch.object(monitor, "_appointment_panel_is_visible", return_value=True),
                patch.object(monitor, "select_available_site", return_value=object()),
                patch.object(
                    monitor,
                    "read_appointment_availability",
                    return_value=_available_result(),
                ),
                patch.object(
                    monitor, "select_available_appointment", return_value=recovered
                ),
                patch.object(
                    monitor,
                    "capture_canonical_selected_slot",
                    side_effect=lambda *_args, **_kwargs: (
                        calls.append("archive") or recovered,
                        recovered_slot,
                        recovered_slot,
                    ),
                ) as capture,
                patch.object(
                    monitor,
                    "complete_available_reservation",
                    side_effect=lambda *_args, **_kwargs: (
                        calls.append("submit") or registered,
                        recovered_slot,
                        [recovered_slot],
                    ),
                ),
            ):
                result = monitor._reobserve_after_slot_lost(
                    object(),
                    settings,
                    original,
                    original_attempt=1,
                    session_started=time.monotonic(),
                    cancel_event=None,
                    on_check=None,
                    is_allowed_appointment=None,
                    can_submit=None,
                    can_solve_captcha=None,
                    on_submission_intent=None,
                    on_submission_started=None,
                    expected_person_name=None,
                    program_expediente=None,
                    program_plate=None,
                    run_id="run-test",
                    order_id="order-test",
                    ports=_engine_ports(),
                )

            self.assertEqual(calls, ["archive", "submit"])
            self.assertEqual(result[0].status, "registered")
            self.assertEqual(
                capture.call_args.kwargs["phase"], "slot_lost_reobservation"
            )


if __name__ == "__main__":
    unittest.main()
