from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from appointment_bot.browser.whatsapp_web import (
    prepare_whatsapp_web_album,
    prepare_whatsapp_web_documents,
    send_whatsapp_web_appointment_reminder,
    send_whatsapp_web_daily_slot_summary,
    send_whatsapp_web_registration_notice,
    validate_whatsapp_web_session,
)
from appointment_bot.config import Settings
from appointment_bot.db.appointment_reminder_control import (
    get_appointment_reminder_control,
)
from appointment_bot.db.appointment_reminders import (
    get_current_appointment_reminder_candidate,
)
from appointment_bot.db.whatsapp_automation import (
    WhatsAppAutomationJob,
    WhatsAppAutomationStatus,
    block_whatsapp_automation_preflight,
    claim_whatsapp_automation_job,
    finish_whatsapp_automation_job,
    next_waiting_whatsapp_automation_job,
    order_has_sent_whatsapp_message,
    recover_expired_whatsapp_automation_jobs,
    refresh_running_appointment_reminder_snapshot,
    return_running_whatsapp_job_to_blocked,
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
from appointment_bot.services.appointment_reminders import (
    appointment_reminder_message,
    get_current_appointment_reminder_template,
)
from appointment_bot.services.notifier import send_telegram_message
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)
POLL_SECONDS = 1.0
LIMA_TIMEZONE = ZoneInfo("America/Lima")


def _automation_result_detail(result: dict[str, object]) -> str:
    details = [str(result.get("message") or "WhatsApp no confirmo el envio.")]
    delivery_phase = str(result.get("delivery_phase") or "").strip()
    evidence_path = str(result.get("evidence_path") or "").strip()
    if delivery_phase:
        details.append(f"Fase: {delivery_phase}.")
    if evidence_path:
        details.append(f"Evidencia local: {evidence_path}.")
    return " ".join(details)


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
                waiting_job = next_waiting_whatsapp_automation_job(
                    settings=self.settings,
                )
                if waiting_job is None:
                    self._stop_event.wait(POLL_SECONDS)
                    continue
                session = validate_whatsapp_web_session()
                if session.get("status") != "session_ready":
                    message = str(
                        session.get("message")
                        or "WhatsApp Web no confirmó una sesión vinculada."
                    )
                    should_alert = block_whatsapp_automation_preflight(
                        waiting_job["job_key"],
                        error_message=sanitize_text(message),
                        settings=self.settings,
                    )
                    if should_alert:
                        self._notify_preflight_blocked(waiting_job, message)
                    continue
                job = claim_whatsapp_automation_job(
                    waiting_job["job_key"],
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
            "Starting automatic WhatsApp attempt: target=%s kind=%s",
            order_id or job["report_date"],
            job_kind,
        )
        if job_kind == "appointment_reminder":
            refreshed_job, skip_reason = self._revalidate_appointment_reminder(job)
            if refreshed_job is None:
                self._finish(
                    job,
                    status="skipped",
                    error_message=sanitize_text(skip_reason),
                )
                logger.warning(
                    "Appointment reminder skipped before send: job_key=%s reason=%s",
                    job["job_key"],
                    skip_reason,
                )
                return
            job = refreshed_job
        try:
            if (
                order_id is not None
                and job_kind in {"reservation_album", "post_payment_followup"}
                and order_has_sent_whatsapp_message(
                    order_id,
                    job_kind,
                    settings=self.settings,
                )
            ):
                self._finish(job, status="sent")
                logger.info(
                    "Automatic WhatsApp job already satisfied: order_id=%s kind=%s",
                    order_id,
                    job_kind,
                )
                return
            if job_kind == "reservation_album":
                if order_id is None:
                    raise ValueError("El trabajo de evidencia no contiene order_id.")
                message_id, result = self._send_reservation_album(order_id)
            elif job_kind == "post_payment_followup":
                if order_id is None:
                    raise ValueError("El trabajo post-pago no contiene order_id.")
                message_id, result = self._send_post_payment_followup(order_id)
            elif job_kind == "daily_slot_summary":
                message_id, result = self._send_daily_slot_summary(job)
            elif job_kind == "registration_notice":
                message_id, result = self._send_registration_notice(job)
            elif job_kind == "appointment_reminder":
                message_id, result = self._send_appointment_reminder(job)
            else:
                raise ValueError(f"Tipo de trabajo WhatsApp no soportado: {job_kind}")
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
        message = _automation_result_detail(result)
        if result_status == "login_required":
            returned = return_running_whatsapp_job_to_blocked(
                job["job_key"],
                owner_token=self.owner_token,
                error_message=sanitize_text(message),
                settings=self.settings,
            )
            if not returned:
                logger.error(
                    "Could not return WhatsApp job to blocked preflight: %s",
                    job["job_key"],
                )
            self._notify_preflight_blocked(job, message)
            return
        final_status = (
            "uncertain"
            if result_status in {"web_unavailable", "send_uncertain"}
            else "failed"
        )
        self._finish(
            job,
            status=final_status,
            message_id=message_id,
            error_message=sanitize_text(message),
        )
        self._notify_failure(job, final_status, message, result=result)

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

    def _send_daily_slot_summary(
        self,
        job: WhatsAppAutomationJob,
    ) -> tuple[str, dict[str, object]]:
        recipient_phone = job["recipient_phone"]
        message_text = job["message_text"]
        publication_text = job["publication_text"]
        if not recipient_phone or message_text is None or not publication_text:
            raise ValueError(
                "El trabajo del resumen diario no contiene destinatario o textos."
            )
        message_id = job["job_key"]
        result = send_whatsapp_web_daily_slot_summary(
            message_id=message_id,
            recipient_phone=recipient_phone,
            message_text=message_text,
            publication_text=publication_text,
            attachment_paths=job["attachment_paths"],
        )
        return message_id, result

    def _send_registration_notice(
        self,
        job: WhatsAppAutomationJob,
    ) -> tuple[str, dict[str, object]]:
        recipient_phone = job["recipient_phone"]
        recipient_username = job["recipient_username"]
        message_text = job["message_text"]
        if (
            job["order_id"] is None
            or not (recipient_phone or recipient_username)
            or not message_text
        ):
            raise ValueError(
                "El trabajo del aviso de registro no contiene orden, destinatario o texto."
            )
        message_id = job["job_key"]
        result = send_whatsapp_web_registration_notice(
            message_id=message_id,
            recipient_phone=recipient_phone,
            recipient_username=recipient_username,
            message_text=message_text,
        )
        return message_id, result

    def _send_appointment_reminder(
        self,
        job: WhatsAppAutomationJob,
    ) -> tuple[str, dict[str, object]]:
        recipient_phone = job["recipient_phone"]
        recipient_username = job["recipient_username"]
        message_text = job["message_text"]
        if (
            job["order_id"] is None
            or job["reservation_id"] is None
            or not (recipient_phone or recipient_username)
            or not message_text
        ):
            raise ValueError(
                "El recordatorio no contiene reserva, destinatario o texto."
            )
        message_id = job["job_key"]
        result = send_whatsapp_web_appointment_reminder(
            message_id=message_id,
            recipient_phone=recipient_phone,
            recipient_username=recipient_username,
            message_text=message_text,
        )
        self._stop_event.wait(self.settings.appointment_reminders_send_interval_seconds)
        return message_id, result

    def _revalidate_appointment_reminder(
        self,
        job: WhatsAppAutomationJob,
    ) -> tuple[WhatsAppAutomationJob | None, str]:
        reservation_id = job["reservation_id"]
        appointment_day_raw = job["appointment_day"]
        if reservation_id is None or appointment_day_raw is None:
            return None, "El trabajo no conserva reserva o fecha de cita."
        try:
            appointment_day = date.fromisoformat(appointment_day_raw)
        except ValueError:
            return None, "La fecha normalizada del recordatorio es invalida."
        expected_day = datetime.now(LIMA_TIMEZONE).date() + timedelta(days=1)
        if appointment_day != expected_day:
            return None, (
                "El recordatorio ya no corresponde al dia siguiente en America/Lima."
            )
        candidate = get_current_appointment_reminder_candidate(
            reservation_id,
            appointment_day,
            settings=self.settings,
        )
        if candidate is None:
            return None, "La reserva dejo de ser la cita confirmada vigente de la orden."
        control = get_appointment_reminder_control(self.settings)
        order_id = job["order_id"] or ""
        if not control.allows(order_id):
            return None, "El control vigente ya no autoriza este recordatorio."
        template = get_current_appointment_reminder_template(self.settings)
        try:
            refreshed = refresh_running_appointment_reminder_snapshot(
                job["job_key"],
                owner_token=self.owner_token,
                recipient_phone=candidate["recipient_phone"],
                recipient_username=candidate["recipient_username"],
                message_text=appointment_reminder_message(
                    candidate,
                    template.message_template,
                ),
                template_key=template.template_key,
                template_revision=template.revision,
                settings=self.settings,
            )
        except ValueError as exc:
            return None, f"El contacto vigente no es utilizable: {exc}"
        if refreshed is None:
            return None, "La propiedad del trabajo cambio durante la revalidacion."
        return refreshed, ""

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
        *,
        result: dict[str, object] | None = None,
    ) -> None:
        flow = (
            "evidencia y cobro"
            if job["job_kind"] == "reservation_album"
            else (
                "documentos post-pago"
                if job["job_kind"] == "post_payment_followup"
                else (
                    "aviso de registro"
                    if job["job_kind"] == "registration_notice"
                    else (
                        "recordatorio de cita"
                        if job["job_kind"] == "appointment_reminder"
                        else "resumen diario de cupos"
                    )
                )
            )
        )
        target = (
            f"Orden: {job['order_id']}"
            if job["order_id"] is not None
            else f"Fecha: {job['report_date']}"
        )
        component_lines: list[str] = []
        if result is not None and job["job_kind"] in {
            "daily_slot_summary",
            "post_payment_followup",
        }:
            components = result.get("delivery_components")
            if isinstance(components, dict):
                labels = {
                    "summary": "Resumen",
                    "images": "Imágenes",
                    "publication": "Publicación TikTok",
                }
                if job["job_kind"] == "post_payment_followup":
                    labels.update(
                        {
                            "documents": "PDFs",
                            "payment_confirmation": "Mensaje de pago confirmado",
                        }
                    )
                    component_keys = ("documents", "payment_confirmation")
                else:
                    component_keys = ("summary", "images", "publication")
                states = {
                    "confirmed": "confirmado",
                    "skipped": "omitidas porque no había archivos",
                    "uncertain": "no confirmado automáticamente",
                    "not_attempted": "no intentado",
                }
                for key in component_keys:
                    value = str(components.get(key) or "not_attempted")
                    component_lines.append(
                        f"{labels[key]}: {states.get(value, value)}"
                    )
        send_telegram_message(
            self.settings,
            "\n".join(
                [
                    "⚠️ Envío automático de WhatsApp no confirmado.",
                    target,
                    f"Flujo: {flow}",
                    f"Estado: {status}",
                    *component_lines,
                    f"Detalle: {sanitize_text(message)}",
                    "No se realizará otro intento automático. Revisar desde el dashboard.",
                ]
            ),
        )

    def _notify_preflight_blocked(
        self,
        job: WhatsAppAutomationJob,
        message: str,
    ) -> None:
        flow = (
            "evidencia y cobro"
            if job["job_kind"] == "reservation_album"
            else (
                "documentos post-pago"
                if job["job_kind"] == "post_payment_followup"
                else (
                    "aviso de registro"
                    if job["job_kind"] == "registration_notice"
                    else (
                        "recordatorio de cita"
                        if job["job_kind"] == "appointment_reminder"
                        else "resumen diario de cupos"
                    )
                )
            )
        )
        target = (
            f"Orden: {job['order_id']}"
            if job["order_id"] is not None
            else f"Fecha: {job['report_date']}"
        )
        send_telegram_message(
            self.settings,
            "\n".join(
                [
                    "⚠️ WhatsApp automático quedó esperando una sesión válida.",
                    target,
                    f"Flujo: {flow}",
                    f"Detalle: {sanitize_text(message)}",
                    "Todavía no se adjuntaron archivos ni se consumió el intento de envío.",
                ]
            ),
        )


__all__ = ["WhatsAppAutomationDispatcher"]
