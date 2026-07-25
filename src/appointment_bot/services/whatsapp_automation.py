from __future__ import annotations

import logging
import threading
from uuid import uuid4

from appointment_bot.browser.whatsapp_web import (
    prepare_whatsapp_web_album,
    prepare_whatsapp_web_documents,
)
from appointment_bot.config import Settings
from appointment_bot.db.whatsapp_automation import (
    WhatsAppAutomationJob,
    WhatsAppAutomationStatus,
    claim_next_whatsapp_automation_job,
    finish_whatsapp_automation_job,
    order_has_sent_whatsapp_message,
    recover_expired_whatsapp_automation_jobs,
)
from appointment_bot.db.whatsapp_followup_messages import (
    get_followup_web_draft,
    mark_followup_message_sent,
    prepare_post_payment_whatsapp_message,
)
from appointment_bot.db.whatsapp_messages import (
    get_whatsapp_web_draft,
    mark_whatsapp_message_sent,
    prepare_order_whatsapp_message,
)
from appointment_bot.services.notifier import send_telegram_message
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)
POLL_SECONDS = 1.0


class WhatsAppAutomationDispatcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.owner_token = f"whatsapp-automation-{uuid4().hex}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="whatsapp-automation-dispatcher",
            daemon=True,
        )
        self._thread.start()
        logger.info("WhatsApp automation dispatcher started")

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is None:
            return
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("WhatsApp automation dispatcher is still finishing an active attempt")
        else:
            logger.info("WhatsApp automation dispatcher stopped")
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                expired_jobs = recover_expired_whatsapp_automation_jobs(
                    settings=self.settings,
                )
                for expired_job in expired_jobs:
                    self._notify_failure(
                        expired_job,
                        "uncertain",
                        "El proceso terminó durante el intento automático.",
                    )
                job = claim_next_whatsapp_automation_job(
                    self.owner_token,
                    settings=self.settings,
                )
            except Exception:
                logger.exception("Could not claim a WhatsApp automation job")
                self._stop_event.wait(POLL_SECONDS)
                continue
            if job is None:
                self._stop_event.wait(POLL_SECONDS)
                continue
            try:
                self._process_job(job)
            except Exception:
                logger.exception(
                    "Unexpected WhatsApp automation dispatcher failure: job_key=%s",
                    job["job_key"],
                )

    def _process_job(self, job: WhatsAppAutomationJob) -> None:
        order_id = job["order_id"]
        job_kind = job["job_kind"]
        logger.info(
            "Starting automatic WhatsApp attempt: order_id=%s kind=%s",
            order_id,
            job_kind,
        )
        try:
            if order_has_sent_whatsapp_message(
                order_id,
                job_kind,
                settings=self.settings,
            ):
                self._finish(job, status="sent")
                logger.info(
                    "Automatic WhatsApp job already satisfied: order_id=%s kind=%s",
                    order_id,
                    job_kind,
                )
                return
            if job_kind == "reservation_album":
                message_id, result = self._send_reservation_album(order_id)
            else:
                message_id, result = self._send_post_payment_followup(order_id)
        except Exception as exc:
            logger.exception(
                "Automatic WhatsApp preparation failed: order_id=%s kind=%s",
                order_id,
                job_kind,
            )
            self._finish(
                job,
                status="failed",
                error_message=sanitize_text(str(exc)),
            )
            self._notify_failure(job, "failed", str(exc))
            return

        if result.get("sent"):
            self._finish(job, status="sent", message_id=message_id)
            logger.info(
                "Automatic WhatsApp attempt completed: order_id=%s kind=%s message_id=%s",
                order_id,
                job_kind,
                message_id,
            )
            return

        result_status = str(result.get("status") or "unknown")
        message = str(result.get("message") or "WhatsApp no confirmó el envío.")
        final_status = "uncertain" if result_status == "web_unavailable" else "failed"
        self._finish(
            job,
            status=final_status,
            message_id=message_id,
            error_message=sanitize_text(message),
        )
        self._notify_failure(job, final_status, message)

    def _send_reservation_album(
        self,
        order_id: str,
    ) -> tuple[str, dict[str, object]]:
        prepared = prepare_order_whatsapp_message(
            order_id,
            automatic=True,
            settings=self.settings,
        )
        message_id = str(prepared["message_id"])
        confirmation = get_whatsapp_web_draft(
            message_id,
            draft_kind="confirmation",
            settings=self.settings,
        )
        payment = get_whatsapp_web_draft(
            message_id,
            draft_kind="payment",
            settings=self.settings,
        )
        result = prepare_whatsapp_web_album(confirmation, payment, auto_send=True)
        if result.get("sent"):
            mark_whatsapp_message_sent(message_id, settings=self.settings)
        return message_id, result

    def _send_post_payment_followup(
        self,
        order_id: str,
    ) -> tuple[str, dict[str, object]]:
        prepared = prepare_post_payment_whatsapp_message(
            order_id,
            automatic=True,
            settings=self.settings,
        )
        message_id = str(prepared["message_id"])
        draft = get_followup_web_draft(message_id, settings=self.settings)
        result = prepare_whatsapp_web_documents(draft)
        if result.get("sent"):
            mark_followup_message_sent(message_id, settings=self.settings)
        return message_id, result

    def _finish(
        self,
        job: WhatsAppAutomationJob,
        *,
        status: WhatsAppAutomationStatus,
        message_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        updated = finish_whatsapp_automation_job(
            job["job_key"],
            owner_token=self.owner_token,
            status=status,
            message_id=message_id,
            error_message=error_message,
            settings=self.settings,
        )
        if not updated:
            logger.error(
                "WhatsApp automation job ownership changed before completion: %s",
                job["job_key"],
            )

    def _notify_failure(
        self,
        job: WhatsAppAutomationJob,
        status: str,
        message: str,
    ) -> None:
        flow = (
            "evidencia y cobro"
            if job["job_kind"] == "reservation_album"
            else "documentos post-pago"
        )
        send_telegram_message(
            self.settings,
            "\n".join(
                [
                    "⚠️ Envío automático de WhatsApp no confirmado.",
                    f"Orden: {job['order_id']}",
                    f"Flujo: {flow}",
                    f"Estado: {status}",
                    f"Detalle: {sanitize_text(message)}",
                    "No se realizará otro intento automático. Revisar desde el dashboard.",
                ]
            ),
        )


__all__ = ["WhatsAppAutomationDispatcher"]
