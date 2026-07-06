from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from appointment_bot.domain import AvailabilityResult, RunReport
from appointment_bot.services.notifier import (
    notify_deferred_queue_summary,
    notify_immediate_availability,
    notify_result,
)
from tests.helpers import make_settings


class NotifierTests(unittest.TestCase):
    def test_partial_without_hour_is_not_sent_to_telegram(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = AvailabilityResult(
                status="partial",
                message="Se detecto fecha disponible, pero aun no hay hora seleccionable.",
                details={"fecha": "04/07/2026", "hora": "Sin Cupos"},
            )

            with patch("appointment_bot.services.notifier.send_telegram_message") as send:
                delivered = notify_result(result, settings)

            send.assert_not_called()
            self.assertFalse(delivered)

    def test_partial_with_blocked_rule_evidence_is_sent_to_telegram(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = AvailabilityResult(
                status="partial",
                message="Se encontro un horario disponible, pero no cumple la regla.",
                details={
                    "fecha": "04/07/2026",
                    "hora": "10:00",
                    "blocked_selected_for_evidence": True,
                    "submission_outcome": "blocked_by_order_rule",
                },
            )

            with patch(
                "appointment_bot.services.notifier.send_telegram_message",
                return_value=True,
            ) as send:
                delivered = notify_result(result, settings)

            send.assert_called_once()
            self.assertTrue(delivered)

    def test_blocked_rule_partial_sends_immediate_text_alert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = AvailabilityResult(
                status="partial",
                message="Se encontro un horario disponible, pero no cumple la regla.",
                details={
                    "orden": "order-123",
                    "cliente": "Mayra",
                    "sede": "LIMA-LA VICTORIA",
                    "fecha": "08/07/2026",
                    "hora": "10:00",
                    "blocked_by_order_rule": True,
                    "submission_outcome": "blocked_by_order_rule",
                },
            )

            with patch(
                "appointment_bot.services.notifier.send_telegram_message",
                return_value=True,
            ) as send:
                delivered = notify_immediate_availability(result, settings)

            self.assertTrue(delivered)
            message = send.call_args.args[1]
            self.assertIn("CUPO DETECTADO", message)
            self.assertIn("Enviado:", message)
            self.assertIn("Lima", message)
            self.assertIn("Sede: LIMA-LA VICTORIA", message)
            self.assertIn("Fechas: 08/07/2026", message)
            self.assertIn("Horas: 10:00", message)
            self.assertIn("Cupos: no registrado", message)
            self.assertIn("08/07/2026", message)
            self.assertIn("10:00", message)
            self.assertNotIn("order-123", message)
            self.assertNotIn("Mayra", message)
            self.assertNotIn("Orden:", message)
            self.assertNotIn("Cliente:", message)
            self.assertNotIn("Cuenta:", message)
            self.assertNotIn("pasara al siguiente usuario", message)
            self.assertEqual(send.call_args.kwargs["timeout_seconds"], 5)

    def test_immediate_available_alert_uses_options_and_slots_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = AvailabilityResult(
                status="available",
                message="Hay horarios.",
                details={
                    "orden": "order-123",
                    "cliente": "Mayra",
                    "cuenta": "usuario@example.com",
                    "sede": "LIMA-LA VICTORIA",
                    "date_options": ["16/07/2026", "20/07/2026"],
                    "hour_options": ["08:00", "10:00"],
                    "cupos": 2,
                },
            )

            with patch(
                "appointment_bot.services.notifier.send_telegram_message",
                return_value=True,
            ) as send:
                delivered = notify_immediate_availability(result, settings)

            self.assertTrue(delivered)
            message = send.call_args.args[1]
            self.assertIn("CUPO DETECTADO", message)
            self.assertIn("Fechas: 16/07/2026, 20/07/2026", message)
            self.assertIn("Horas: 08:00, 10:00", message)
            self.assertIn("Cupos: 2", message)
            self.assertNotIn("order-123", message)
            self.assertNotIn("Mayra", message)
            self.assertNotIn("usuario@example.com", message)

    def test_deferred_summary_sends_only_primary_non_captcha_photo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_path = Path(directory)
            settings = make_settings(base_path)
            captcha_path = base_path / "captcha.png"
            panel_path = base_path / "panel-completo.png"
            captcha_path.write_bytes(b"captcha")
            panel_path.write_bytes(b"panel")
            queue_report = RunReport(
                status="completed",
                message="Cola rapida terminada.",
                exit_code=0,
            )
            deferred = RunReport(
                status="partial",
                message="Se encontro un horario disponible, pero no cumple la regla.",
                exit_code=0,
                details={
                    "fecha": "08/07/2026",
                    "hora": "10:00",
                    "submission_outcome": "blocked_by_order_rule",
                },
                screenshot_paths=[str(captcha_path), str(panel_path)],
            )

            with (
                patch(
                    "appointment_bot.services.notifier.send_telegram_message",
                    return_value=True,
                ) as send_message,
                patch(
                    "appointment_bot.services.notifier.send_telegram_photo",
                    return_value=True,
                ) as send_photo,
            ):
                delivered = notify_deferred_queue_summary(
                    queue_report,
                    settings,
                    [deferred],
                )

            self.assertTrue(delivered)
            send_message.assert_not_called()
            send_photo.assert_called_once()
            self.assertEqual(send_photo.call_args.args[1], panel_path)


if __name__ == "__main__":
    unittest.main()
