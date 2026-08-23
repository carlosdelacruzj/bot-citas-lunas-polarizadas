from __future__ import annotations

import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from appointment_bot.services.api.appointment_reminder_routes import (
    appointment_reminders_payload,
    update_appointment_reminders_payload,
)
from appointment_bot.services.api.captcha_authority_routes import (
    captcha_authority_control_payload,
    update_captcha_authority_control_payload,
)
from appointment_bot.services.api.captcha_sampling_routes import (
    captcha_sampling_control_payload,
    update_captcha_sampling_control_payload,
)
from appointment_bot.services.api.captcha_shadow_routes import (
    captcha_shadow_dataset_export_payload,
    captcha_shadow_events_payload,
    captcha_shadow_human_label_event_id,
    captcha_shadow_image_event_id,
    captcha_shadow_image_payload,
    captcha_shadow_quality_cases_payload,
    captcha_shadow_quality_payload,
    captcha_shadow_summary_payload,
    save_captcha_shadow_human_label_payload,
)
from appointment_bot.services.api.finance_routes import (
    create_finance_entry_payload,
    finance_categories_payload,
    finance_data_quality_payload,
    finance_entries_payload,
    finance_entry_action_path,
    finance_month_closure_payload,
    finance_payment_reconciliation_path,
    finance_summary_payload,
    reconcile_payment_amount_payload,
    update_finance_entry_payload,
    upsert_finance_month_closure_payload,
    void_finance_entry_payload,
)
from appointment_bot.services.api.http import (
    RequestBodyError,
    error_payload,
    read_json,
    require_authorized,
    send_download,
    send_image,
    send_json,
    send_png,
)
from appointment_bot.services.api.manual_session_routes import (
    close_manual_session_payload,
    list_manual_sessions_payload,
    open_manual_session_payload,
)
from appointment_bot.services.api.monthly_dashboard_routes import monthly_dashboard_payload
from appointment_bot.services.api.monthly_dashboard_v2_routes import monthly_dashboard_v2_payload
from appointment_bot.services.api.operator_inbox_routes import operator_inbox_payload
from appointment_bot.services.api.opportunity_routes import (
    opportunity_burst_id,
    opportunity_burst_payload,
    opportunity_bursts_payload,
    opportunity_control_payload,
    update_opportunity_control_payload,
)
from appointment_bot.services.api.post_appointment_routes import (
    post_appointment_followups_payload,
    post_appointment_review_order_id,
    review_post_appointment_payload,
)
from appointment_bot.services.api.run_routes import get_run_payload, list_runs_payload
from appointment_bot.services.api.service_order_routes import (
    apply_service_order_action,
    close_service_order_payload,
    create_service_order_payload,
    get_service_order_credentials_payload,
    get_service_order_payload,
    list_service_orders_payload,
    mark_payment_paid_payload,
    payment_paid_path,
    payment_partial_path,
    record_partial_payment_payload,
    revalidate_service_order_payload,
    search_service_orders_payload,
    service_order_action,
    service_order_close_path,
    service_order_contact_path,
    service_order_credentials_path,
    service_order_priority_path,
    service_order_restrictions_path,
    service_order_revalidate_path,
    service_order_split_programs_path,
    split_service_order_programs_payload,
    update_service_order_contact_payload,
    update_service_order_credentials_payload,
    update_service_order_priority_payload,
    update_service_order_restrictions_payload,
)
from appointment_bot.services.api.whatsapp_routes import (
    attachment_payload,
    followup_attachment_payload,
    mark_followup_sent_payload,
    mark_sent_payload,
    order_followup_prepare_path,
    order_prepare_path,
    order_whatsapp_review_path,
    payment_attachment_payload,
    prepare_followup_payload,
    prepare_followup_test_payload,
    prepare_followup_web_payload,
    prepare_order_payload,
    prepare_test_payload,
    prepare_web_payload,
    resolve_whatsapp_review_payload,
    validate_whatsapp_session_payload,
    whatsapp_followup_message_path,
    whatsapp_message_path,
    whatsapp_review_job_path,
    whatsapp_review_payload,
)
from appointment_bot.services.api.worker_routes import (
    enqueue_restart_with_safe_backoff_release_payload,
    enqueue_worker_command_payload,
    health_payload,
    list_worker_commands_payload,
    record_worker_control_audit,
    worker_payload,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class LocalApiHandler(BaseHTTPRequestHandler):
    server_version = "AppointmentBotLocalApi/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            controller = getattr(self.server, "worker_controller", None)
            healthy, payload = health_payload(controller)
            self._send_json(HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE, payload)
            return

        if path == "/api/v1/worker":
            if not self._require_authorized(strict=True):
                return
            self._send_json(
                HTTPStatus.OK,
                worker_payload(getattr(self.server, "worker_controller", None)),
            )
            return

        if path == "/api/v1/worker/commands":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, list_worker_commands_payload(query))
            return

        if path == "/api/v1/runtime-controls/captcha-sampling":
            if not self._require_authorized(strict=True):
                return
            status, payload = captcha_sampling_control_payload()
            self._send_json(status, payload)
            return

        if path == "/api/v1/runtime-controls/captcha-authority":
            if not self._require_authorized(strict=True):
                return
            status, payload = captcha_authority_control_payload()
            self._send_json(status, payload)
            return

        if path == "/api/v1/runtime-controls/opportunity":
            if not self._require_authorized(strict=True):
                return
            status, payload = opportunity_control_payload()
            self._send_json(status, payload)
            return

        if path == "/api/v1/opportunity-bursts":
            if not self._require_authorized(strict=True):
                return
            status, payload = opportunity_bursts_payload(query)
            self._send_json(status, payload)
            return

        if path == "/api/v1/appointment-reminders":
            if not self._require_authorized(strict=True):
                return
            status, payload = appointment_reminders_payload()
            self._send_json(status, payload)
            return

        burst_id = opportunity_burst_id(path)
        if burst_id is not None:
            if not self._require_authorized(strict=True):
                return
            if not burst_id:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    error_payload("not_found", "Rafaga no encontrada."),
                )
                return
            status, payload = opportunity_burst_payload(burst_id)
            self._send_json(status, payload)
            return

        if path == "/api/v1/manual-sessions":
            if not self._require_authorized(strict=True):
                return
            status, payload = list_manual_sessions_payload()
            self._send_json(status, payload)
            return

        if path == "/api/v1/captcha-shadow/summary":
            if not self._require_authorized(strict=True):
                return
            status, payload = captcha_shadow_summary_payload()
            self._send_json(status, payload)
            return

        if path == "/api/v1/captcha-shadow/events":
            if not self._require_authorized(strict=True):
                return
            status, payload = captcha_shadow_events_payload(query)
            self._send_json(status, payload)
            return

        if path == "/api/v1/captcha-shadow/quality":
            if not self._require_authorized(strict=True):
                return
            status, payload = captcha_shadow_quality_payload()
            self._send_json(status, payload)
            return

        if path == "/api/v1/captcha-shadow/quality/cases":
            if not self._require_authorized(strict=True):
                return
            status, payload = captcha_shadow_quality_cases_payload(query)
            self._send_json(status, payload)
            return

        if path == "/api/v1/captcha-shadow/dataset/export":
            if not self._require_authorized(strict=True):
                return
            status, payload = captcha_shadow_dataset_export_payload()
            if isinstance(payload, dict):
                self._send_json(status, payload)
            else:
                send_download(
                    self,
                    payload,
                    filename="captcha-human-validated-dataset.zip",
                    content_type="application/zip",
                )
            return

        captcha_event_id = captcha_shadow_image_event_id(path)
        if captcha_event_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = captcha_shadow_image_payload(captcha_event_id)
            if isinstance(payload, dict):
                self._send_json(status, payload)
            else:
                send_image(self, payload)
            return

        if path == "/api/v1/service-orders":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, list_service_orders_payload())
            return

        if path == "/api/v1/operator-inbox":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, operator_inbox_payload())
            return

        if path == "/api/v1/post-appointment-followups":
            if not self._require_authorized(strict=True):
                return
            status, payload = post_appointment_followups_payload()
            self._send_json(status, payload)
            return

        if path == "/api/v1/monthly-summary":
            if not self._require_authorized(strict=True):
                return
            status, payload = monthly_dashboard_payload(query)
            self._send_json(status, payload)
            return

        if path == "/api/v2/monthly-summary":
            if not self._require_authorized(strict=True):
                return
            status, payload = monthly_dashboard_v2_payload(query)
            self._send_json(status, payload)
            return

        if path == "/api/v1/finance/categories":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, finance_categories_payload())
            return

        if path == "/api/v1/finance/entries":
            if not self._require_authorized(strict=True):
                return
            status, payload = finance_entries_payload(query)
            self._send_json(status, payload)
            return

        if path == "/api/v1/finance/summary":
            if not self._require_authorized(strict=True):
                return
            status, payload = finance_summary_payload(query)
            self._send_json(status, payload)
            return

        if path == "/api/v1/finance/data-quality":
            if not self._require_authorized(strict=True):
                return
            status, payload = finance_data_quality_payload(query)
            self._send_json(status, payload)
            return

        if path == "/api/v1/finance/month-closure":
            if not self._require_authorized(strict=True):
                return
            status, payload = finance_month_closure_payload(query)
            self._send_json(status, payload)
            return

        attachment_message_id = whatsapp_message_path(path, "attachment")
        if attachment_message_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = attachment_payload(attachment_message_id)
            if isinstance(payload, dict):
                self._send_json(status, payload)
            else:
                send_png(self, payload)
            return

        payment_attachment_message_id = whatsapp_message_path(path, "payment-attachment")
        if payment_attachment_message_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = payment_attachment_payload(payment_attachment_message_id)
            if isinstance(payload, dict):
                self._send_json(status, payload)
            else:
                send_image(self, payload)
            return

        if path.startswith("/api/v1/whatsapp-followup-messages/") and "/attachments/" in path:
            if not self._require_authorized(strict=True):
                return
            parts = path.removeprefix("/api/v1/whatsapp-followup-messages/").split("/attachments/")
            if len(parts) != 2:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    error_payload("not_found", "Adjunto no encontrado."),
                )
                return
            message_id, suffix = parts
            try:
                step_text, attachment_text = suffix.split("/", 1)
                step_index = int(step_text)
                attachment_index = int(attachment_text)
            except ValueError:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    error_payload("not_found", "Adjunto no encontrado."),
                )
                return
            status, payload = followup_attachment_payload(
                message_id,
                step_index,
                attachment_index,
            )
            if isinstance(payload, dict):
                self._send_json(status, payload)
            else:
                send_image(self, payload)
            return

        if path.startswith("/api/v1/service-orders/"):
            if not self._require_authorized(strict=True):
                return
            followup_review_order_id = order_whatsapp_review_path(
                path, "whatsapp-followup"
            )
            if followup_review_order_id is not None:
                status, payload = whatsapp_review_payload(
                    followup_review_order_id,
                    job_kind="post_payment_followup",
                )
                self._send_json(status, payload)
                return
            message_review_order_id = order_whatsapp_review_path(path, "whatsapp")
            if message_review_order_id is not None:
                status, payload = whatsapp_review_payload(
                    message_review_order_id,
                    job_kind="reservation_album",
                )
                self._send_json(status, payload)
                return
            credentials_result = get_service_order_credentials_payload(path)
            if credentials_result is not None:
                status, payload = credentials_result
                self._send_json(status, payload)
                return
            result = get_service_order_payload(path)
            if result is not None:
                status, payload = result
                self._send_json(status, payload)
                return

        if path == "/api/v1/runs":
            if not self._require_authorized(strict=True):
                return
            self._send_json(HTTPStatus.OK, list_runs_payload(query))
            return

        if path.startswith("/api/v1/runs/"):
            if not self._require_authorized(strict=True):
                return
            status, payload = get_run_payload(path, query)
            self._send_json(status, payload)
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            error_payload(
                "not_found",
                "Use GET /health or the /api/v1 endpoints.",
            ),
        )

    def do_POST(self) -> None:
        try:
            self._handle_post()
        except RequestBodyError as exc:
            self._send_json(
                exc.status,
                error_payload("bad_request", str(exc)),
            )

    def _handle_post(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/v1/appointment-reminders":
            if not self._require_authorized(strict=True):
                return
            status, payload = update_appointment_reminders_payload(
                self._read_json(),
                requested_by=self.headers.get("X-Appointment-Actor"),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/runtime-controls/captcha-sampling":
            if not self._require_authorized(strict=True):
                return
            status, payload = update_captcha_sampling_control_payload(
                self._read_json(),
                requested_by=self.headers.get("X-Appointment-Actor"),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/runtime-controls/captcha-authority":
            if not self._require_authorized(strict=True):
                return
            status, payload = update_captcha_authority_control_payload(
                self._read_json(),
                requested_by=self.headers.get("X-Appointment-Actor"),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/runtime-controls/opportunity":
            if not self._require_authorized(strict=True):
                return
            status, payload = update_opportunity_control_payload(
                self._read_json(),
                requested_by=self.headers.get("X-Appointment-Actor"),
            )
            self._send_json(status, payload)
            return

        captcha_event_id = captcha_shadow_human_label_event_id(path)
        if captcha_event_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = save_captcha_shadow_human_label_payload(
                captcha_event_id,
                self._read_json(),
                reviewer=self.headers.get("X-Appointment-Actor") or "dashboard-owner",
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/service-orders":
            if not self._require_authorized(strict=True):
                return
            status, payload = create_service_order_payload(self._read_json())
            self._send_json(status, payload)
            return

        if path == "/api/v1/service-orders/search":
            if not self._require_authorized(strict=True):
                return
            payload = self._read_json()
            self._send_json(
                HTTPStatus.OK,
                search_service_orders_payload(str(payload.get("query") or "")),
            )
            return

        post_appointment_order_id = post_appointment_review_order_id(path)
        if post_appointment_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = review_post_appointment_payload(post_appointment_order_id)
            self._send_json(status, payload)
            return

        if path == "/api/v1/whatsapp-messages/test/prepare":
            if not self._require_authorized(strict=True):
                return
            status, payload = prepare_test_payload(self._read_json())
            self._send_json(status, payload)
            return

        if path == "/api/v1/whatsapp-followup-messages/test/prepare":
            if not self._require_authorized(strict=True):
                return
            status, payload = prepare_followup_test_payload(self._read_json())
            self._send_json(status, payload)
            return

        if path == "/api/v1/whatsapp-web/session/validate":
            if not self._require_authorized(strict=True):
                return
            status, payload = validate_whatsapp_session_payload(
                server_host=str(self.server.server_address[0]),
                client_host=str(self.client_address[0]),
            )
            self._send_json(status, payload)
            return

        whatsapp_order_id = order_prepare_path(path)
        if whatsapp_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = prepare_order_payload(whatsapp_order_id, self._read_json())
            self._send_json(status, payload)
            return

        whatsapp_message_id = whatsapp_message_path(path, "sent")
        if whatsapp_message_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = mark_sent_payload(whatsapp_message_id)
            self._send_json(status, payload)
            return

        whatsapp_web_message_id = whatsapp_message_path(path, "web/prepare")
        if whatsapp_web_message_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = prepare_web_payload(
                whatsapp_web_message_id,
                payload=self._read_json(),
                server_host=str(self.server.server_address[0]),
                client_host=str(self.client_address[0]),
            )
            self._send_json(status, payload)
            return

        whatsapp_followup_order_id = order_followup_prepare_path(path)
        if whatsapp_followup_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = prepare_followup_payload(
                whatsapp_followup_order_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        whatsapp_followup_web_message_id = whatsapp_followup_message_path(path, "web/prepare")
        if whatsapp_followup_web_message_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = prepare_followup_web_payload(
                whatsapp_followup_web_message_id,
                server_host=str(self.server.server_address[0]),
                client_host=str(self.client_address[0]),
            )
            self._send_json(status, payload)
            return

        whatsapp_followup_message_id = whatsapp_followup_message_path(path, "sent")
        if whatsapp_followup_message_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = mark_followup_sent_payload(whatsapp_followup_message_id)
            self._send_json(status, payload)
            return

        whatsapp_review_job_key = whatsapp_review_job_path(path)
        if whatsapp_review_job_key is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = resolve_whatsapp_review_payload(
                whatsapp_review_job_key,
                self._read_json(),
                requested_by=self.headers.get("X-Appointment-Actor"),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/finance/entries":
            if not self._require_authorized(strict=True):
                return
            status, payload = create_finance_entry_payload(self._read_json())
            self._send_json(status, payload)
            return

        finance_edit_id = finance_entry_action_path(path, "edit")
        if finance_edit_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = update_finance_entry_payload(finance_edit_id, self._read_json())
            self._send_json(status, payload)
            return

        finance_void_id = finance_entry_action_path(path, "void")
        if finance_void_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = void_finance_entry_payload(finance_void_id, self._read_json())
            self._send_json(status, payload)
            return

        if path == "/api/v1/finance/month-closure":
            if not self._require_authorized(strict=True):
                return
            status, payload = upsert_finance_month_closure_payload(self._read_json())
            self._send_json(status, payload)
            return

        finance_payment_id = finance_payment_reconciliation_path(path)
        if finance_payment_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = reconcile_payment_amount_payload(
                finance_payment_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        contact_order_id = service_order_contact_path(path)
        if contact_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = update_service_order_contact_payload(
                contact_order_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        credentials_order_id = service_order_credentials_path(path)
        if credentials_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = update_service_order_credentials_payload(
                credentials_order_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        priority_order_id = service_order_priority_path(path)
        if priority_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = update_service_order_priority_payload(
                priority_order_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        restrictions_order_id = service_order_restrictions_path(path)
        if restrictions_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = update_service_order_restrictions_payload(
                restrictions_order_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        revalidate_order_id = service_order_revalidate_path(path)
        if revalidate_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = revalidate_service_order_payload(revalidate_order_id)
            self._send_json(status, payload)
            return

        paid_order_id = payment_paid_path(path)
        if paid_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = mark_payment_paid_payload(
                paid_order_id,
                self._read_json(),
                requested_by=self.headers.get("X-Appointment-Actor"),
            )
            self._send_json(status, payload)
            return

        partial_order_id = payment_partial_path(path)
        if partial_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = record_partial_payment_payload(
                partial_order_id,
                self._read_json(),
                requested_by=self.headers.get("X-Appointment-Actor"),
            )
            self._send_json(status, payload)
            return

        close_order_id = service_order_close_path(path)
        if close_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = close_service_order_payload(close_order_id, self._read_json())
            self._send_json(status, payload)
            return

        split_order_id = service_order_split_programs_path(path)
        if split_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = split_service_order_programs_payload(
                split_order_id,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        if service_order_action(path) is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = apply_service_order_action(path) or (
                HTTPStatus.NOT_FOUND,
                error_payload("not_found", "Unsupported service order action."),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/worker/restart":
            if not self._require_authorized(strict=True):
                return
            request_payload = self._read_json()
            release_safe_backoffs = request_payload.get("release_safe_backoffs", False)
            if not isinstance(release_safe_backoffs, bool):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    error_payload(
                        "bad_request",
                        "release_safe_backoffs must be a boolean.",
                    ),
                )
                return
            if release_safe_backoffs:
                status, payload = enqueue_restart_with_safe_backoff_release_payload(
                    requested_by=self.headers.get("X-Appointment-Actor"),
                )
                self._send_json(status, payload)
                return
            controller = getattr(self.server, "worker_controller", None)
            restart_callback = getattr(self.server, "restart_callback", None)
            if controller is None or restart_callback is None:
                status, payload = enqueue_worker_command_payload(
                    "restart",
                    requested_by=self.headers.get("X-Appointment-Actor"),
                )
                self._send_json(status, payload)
                return
            controller.prepare_restart()
            controller_settings = getattr(controller, "settings", None)
            if controller_settings is not None:
                record_worker_control_audit(
                    command="restart",
                    requested_by=self.headers.get("X-Appointment-Actor"),
                    status="accepted",
                    detail="control_path=embedded_api",
                    settings=controller_settings,
                )
            self._send_json(
                HTTPStatus.ACCEPTED,
                {"status": "restarting", "message": "Controlled restart requested."},
            )
            restart_callback()
            return

        if path == "/api/v1/manual-session/open":
            if not self._require_authorized(strict=True):
                return
            status, payload = open_manual_session_payload(
                self._read_json(),
                server_host=str(self.server.server_address[0]),
                client_host=str(self.client_address[0]),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/manual-session/close":
            if not self._require_authorized(strict=True):
                return
            status, payload = close_manual_session_payload(self._read_json())
            self._send_json(status, payload)
            return

        if path not in {"/api/v1/worker/pause", "/api/v1/worker/resume"}:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                error_payload("not_found", "Use the /api/v1/worker control endpoints."),
            )
            return

        if not self._require_authorized(strict=True):
            return

        controller = getattr(self.server, "worker_controller", None)
        if controller is None:
            command = "pause" if path.endswith("/pause") else "resume"
            status, payload = enqueue_worker_command_payload(
                command,
                requested_by=self.headers.get("X-Appointment-Actor"),
            )
            self._send_json(status, payload)
            return
        command = "pause" if path.endswith("/pause") else "resume"
        payload = controller.pause() if command == "pause" else controller.resume()
        controller_settings = getattr(controller, "settings", None)
        if controller_settings is not None:
            record_worker_control_audit(
                command=command,
                requested_by=self.headers.get("X-Appointment-Actor"),
                status="applied",
                detail="control_path=embedded_api",
                settings=controller_settings,
            )
        self._send_json(HTTPStatus.OK, payload)

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _require_authorized(self, *, strict: bool = False) -> bool:
        return require_authorized(self, strict=strict)

    def _read_json(self) -> dict[str, Any]:
        return read_json(self)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        send_json(self, status, payload)


def create_local_api_server(
    *,
    worker_controller: Any | None = None,
    restart_callback: Any | None = None,
) -> ThreadingHTTPServer:
    host = os.getenv("APPOINTMENT_BOT_API_HOST", DEFAULT_HOST)
    if (
        host not in {"127.0.0.1", "localhost", "::1"}
        and not os.getenv(
            "APPOINTMENT_BOT_API_TOKEN",
            "",
        ).strip()
    ):
        raise ValueError(
            "APPOINTMENT_BOT_API_TOKEN is required when the local API binds "
            "outside the loopback interface."
        )
    port = int(os.getenv("APPOINTMENT_BOT_API_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer((host, port), LocalApiHandler)
    server.worker_controller = worker_controller
    server.restart_callback = restart_callback
    return server
