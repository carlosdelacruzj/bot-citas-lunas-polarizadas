from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

from appointment_bot.db.whatsapp_automation import WhatsAppAutomationJob
from appointment_bot.services.whatsapp_automation import WhatsAppAutomationDispatcher
from tests.helpers import make_settings


def _registration_job() -> WhatsAppAutomationJob:
    return cast(
        WhatsAppAutomationJob,
        {
            "job_key": "registration:order-1",
            "order_id": "order-1",
            "reservation_id": None,
            "job_kind": "registration_notice",
            "report_date": None,
            "appointment_day": None,
            "recipient_phone": "51987654321",
            "recipient_username": None,
            "message_text": "Aviso",
            "publication_text": None,
            "attachment_paths": [],
            "registration_notice_type": "new_order",
            "preflight_cycle": 0,
            "template_key": None,
            "template_revision": None,
        },
    )


def _album_job() -> WhatsAppAutomationJob:
    job = dict(_registration_job())
    job.update(
        {
            "job_key": "reservation:order-1",
            "job_kind": "reservation_album",
            "message_text": None,
        }
    )
    return cast(WhatsAppAutomationJob, job)


class WhatsAppDeliverySafetyTests(unittest.TestCase):
    def test_browser_exception_after_interaction_is_persisted_as_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dispatcher = WhatsAppAutomationDispatcher(
                make_settings(Path(directory))
            )
            dispatcher._finish = Mock(return_value=True)
            dispatcher._notify_failure = Mock()

            with patch(
                "appointment_bot.services.whatsapp_automation."
                "send_whatsapp_web_registration_notice",
                side_effect=RuntimeError("browser closed after click"),
            ):
                dispatcher._process_job(_registration_job())

            finish_call = dispatcher._finish.call_args
            self.assertEqual(finish_call.kwargs["status"], "uncertain")
            self.assertIn("Fase: interaction_started", finish_call.kwargs["error_message"])
            self.assertIn("Destinatario: ***4321", finish_call.kwargs["error_message"])

    def test_persistence_exception_after_send_is_persisted_as_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dispatcher = WhatsAppAutomationDispatcher(
                make_settings(Path(directory))
            )
            dispatcher._finish = Mock(return_value=True)
            dispatcher._notify_failure = Mock()

            with (
                patch(
                    "appointment_bot.services.whatsapp_automation."
                    "order_has_sent_whatsapp_message",
                    return_value=False,
                ),
                patch(
                    "appointment_bot.services.whatsapp_automation."
                    "prepare_order_whatsapp_message",
                    return_value={"message_id": "message-1"},
                ),
                patch(
                    "appointment_bot.services.whatsapp_automation.get_whatsapp_web_draft",
                    return_value={},
                ),
                patch(
                    "appointment_bot.services.whatsapp_automation.prepare_whatsapp_web_album",
                    return_value={
                        "sent": True,
                        "status": "sent",
                        "evidence_path": ".runtime/whatsapp-sent.png",
                    },
                ),
                patch(
                    "appointment_bot.services.whatsapp_automation.mark_whatsapp_message_sent",
                    side_effect=OSError("database write failed"),
                ),
            ):
                dispatcher._process_job(_album_job())

            finish_call = dispatcher._finish.call_args
            self.assertEqual(finish_call.kwargs["status"], "uncertain")
            self.assertEqual(finish_call.kwargs["message_id"], "message-1")
            self.assertIn("Fase: confirmation_observed", finish_call.kwargs["error_message"])
            self.assertIn(
                "Evidencia local: .runtime/whatsapp-sent.png",
                finish_call.kwargs["error_message"],
            )

    def test_callback_exception_after_confirmation_stays_uncertain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dispatcher = WhatsAppAutomationDispatcher(
                make_settings(Path(directory))
            )
            dispatcher._finish = Mock(return_value=True)
            dispatcher._notify_failure = Mock()

            def fail_after_confirmation(_job, attempt):
                attempt.advance(
                    "confirmation_observed",
                    component="post_send_callback",
                    message_id="message-2",
                )
                raise RuntimeError("callback failed after send")

            dispatcher._send_registration_notice = fail_after_confirmation
            dispatcher._process_job(_registration_job())

            finish_call = dispatcher._finish.call_args
            self.assertEqual(finish_call.kwargs["status"], "uncertain")
            self.assertEqual(finish_call.kwargs["message_id"], "message-2")
            self.assertIn("Componente: post_send_callback", finish_call.kwargs["error_message"])


if __name__ == "__main__":
    unittest.main()
