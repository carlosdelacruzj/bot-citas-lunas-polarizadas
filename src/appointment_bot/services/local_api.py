from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from appointment_bot.manual_session.session import blocking_manual_sessions
from appointment_bot.services.api.appointment_reminder_routes import (
    update_appointment_reminders_payload,
)
from appointment_bot.services.api.captcha_authority_routes import (
    update_captcha_authority_control_payload,
)
from appointment_bot.services.api.captcha_sampling_routes import (
    update_captcha_sampling_control_payload,
)
from appointment_bot.services.api.captcha_shadow_routes import (
    captcha_shadow_human_label_event_id,
    save_captcha_shadow_human_label_payload,
)
from appointment_bot.services.api.finance_routes import (
    create_finance_entry_payload,
    finance_entry_action_path,
    finance_payment_reconciliation_path,
    reconcile_payment_amount_payload,
    update_finance_entry_payload,
    upsert_finance_month_closure_payload,
    void_finance_entry_payload,
)
from appointment_bot.services.api.get_routes import GET_ROUTES
from appointment_bot.services.api.http import (
    RequestBodyError,
    authenticated_actor,
    error_payload,
    read_json,
    require_authorized,
    send_json,
)
from appointment_bot.services.api.manual_session_routes import (
    close_manual_session_payload,
    open_manual_session_payload,
)
from appointment_bot.services.api.opportunity_routes import (
    update_opportunity_control_payload,
)
from appointment_bot.services.api.post_appointment_routes import (
    post_appointment_review_order_id,
    review_post_appointment_payload,
)
from appointment_bot.services.api.routing import ApiRequest, Route, dispatch
from appointment_bot.services.api.service_order_routes import (
    apply_service_order_action,
    close_service_order_payload,
    create_service_order_payload,
    mark_payment_paid_payload,
    payment_paid_path,
    payment_partial_path,
    record_partial_payment_payload,
    resolve_service_order_programs_payload,
    revalidate_service_order_payload,
    search_service_orders_payload,
    service_order_action,
    service_order_close_path,
    service_order_contact_path,
    service_order_credentials_path,
    service_order_priority_path,
    service_order_program_resolution_path,
    service_order_restrictions_path,
    service_order_revalidate_path,
    service_order_split_programs_path,
    split_service_order_programs_payload,
    update_service_order_contact_payload,
    update_service_order_credentials_payload,
    update_service_order_priority_payload,
    update_service_order_restrictions_payload,
)
from appointment_bot.services.api.whatsapp_message_template_routes import (
    preview_whatsapp_message_template_payload,
    update_whatsapp_message_template_payload,
    whatsapp_message_template_action_path,
)
from appointment_bot.services.api.whatsapp_routes import (
    mark_followup_sent_payload,
    mark_sent_payload,
    order_followup_prepare_path,
    order_prepare_path,
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
)
from appointment_bot.services.api.worker_routes import (
    enqueue_restart_with_safe_backoff_release_payload,
    enqueue_worker_command_payload,
    record_worker_control_audit,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class LocalApiHandler(BaseHTTPRequestHandler):
    server_version = "AppointmentBotLocalApi/0.1"

    def do_GET(self) -> None:
        self._dispatch(GET_ROUTES, "Use GET /health or the /api/v1 endpoints.")

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

        template_key = whatsapp_message_template_action_path(path, "preview")
        if template_key is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = preview_whatsapp_message_template_payload(
                template_key,
                self._read_json(),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/appointment-reminders":
            if not self._require_authorized(strict=True):
                return
            status, payload = update_appointment_reminders_payload(
                self._read_json(),
                requested_by=self._authenticated_actor(),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/runtime-controls/captcha-sampling":
            if not self._require_authorized(strict=True):
                return
            status, payload = update_captcha_sampling_control_payload(
                self._read_json(),
                requested_by=self._authenticated_actor(),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/runtime-controls/captcha-authority":
            if not self._require_authorized(strict=True):
                return
            status, payload = update_captcha_authority_control_payload(
                self._read_json(),
                requested_by=self._authenticated_actor(),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/runtime-controls/opportunity":
            if not self._require_authorized(strict=True):
                return
            status, payload = update_opportunity_control_payload(
                self._read_json(),
                requested_by=self._authenticated_actor(),
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
                reviewer=self._authenticated_actor(),
            )
            self._send_json(status, payload)
            return

        if path == "/api/v1/service-orders":
            if not self._require_authorized(strict=True):
                return
            status, payload = create_service_order_payload(
                self._read_json(),
                requested_by=self._authenticated_actor(),
            )
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
                requested_by=self._authenticated_actor(),
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
            status, payload = upsert_finance_month_closure_payload(
                self._read_json(),
                requested_by=self._authenticated_actor(),
            )
            self._send_json(status, payload)
            return

        finance_payment_id = finance_payment_reconciliation_path(path)
        if finance_payment_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = reconcile_payment_amount_payload(
                finance_payment_id,
                self._read_json(),
                requested_by=self._authenticated_actor(),
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
                requested_by=self._authenticated_actor(),
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
                requested_by=self._authenticated_actor(),
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

        program_resolution_order_id = service_order_program_resolution_path(path)
        if program_resolution_order_id is not None:
            if not self._require_authorized(strict=True):
                return
            status, payload = resolve_service_order_programs_payload(
                program_resolution_order_id,
                self._read_json(),
                requested_by=self._authenticated_actor(),
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
            manual_sessions = blocking_manual_sessions()
            if manual_sessions:
                self._send_json(
                    HTTPStatus.CONFLICT,
                    error_payload(
                        "manual_session_active",
                        "No se puede reiniciar mientras exista una sesion manual "
                        "abierta o cerrando.",
                        blocking_session_count=len(manual_sessions),
                        blocking_session_statuses=sorted(
                            {str(item.get("status") or "") for item in manual_sessions}
                        ),
                    ),
                )
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
                    requested_by=self._authenticated_actor(),
                )
                self._send_json(status, payload)
                return
            controller = getattr(self.server, "worker_controller", None)
            restart_callback = getattr(self.server, "restart_callback", None)
            if controller is None or restart_callback is None:
                status, payload = enqueue_worker_command_payload(
                    "restart",
                    requested_by=self._authenticated_actor(),
                )
                self._send_json(status, payload)
                return
            controller.prepare_restart()
            controller_settings = getattr(controller, "settings", None)
            if controller_settings is not None:
                record_worker_control_audit(
                    command="restart",
                    requested_by=self._authenticated_actor(),
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
                requested_by=self._authenticated_actor(),
            )
            self._send_json(status, payload)
            return
        command = "pause" if path.endswith("/pause") else "resume"
        payload = controller.pause() if command == "pause" else controller.resume()
        controller_settings = getattr(controller, "settings", None)
        if controller_settings is not None:
            record_worker_control_audit(
                command=command,
                requested_by=self._authenticated_actor(),
                status="applied",
                detail="control_path=embedded_api",
                settings=controller_settings,
            )
        self._send_json(HTTPStatus.OK, payload)

    def do_PUT(self) -> None:
        try:
            self._handle_put()
        except RequestBodyError as exc:
            self._send_json(
                exc.status,
                error_payload("bad_request", str(exc)),
            )

    def _handle_put(self) -> None:
        path = urlparse(self.path).path
        template_key = whatsapp_message_template_action_path(path)
        if template_key is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                error_payload(
                    "not_found",
                    "Use los endpoints de plantillas de WhatsApp.",
                ),
            )
            return
        if not self._require_authorized(strict=True):
            return
        status, payload = update_whatsapp_message_template_payload(
            template_key,
            self._read_json(),
            requested_by=self._authenticated_actor(),
        )
        self._send_json(status, payload)

    def _dispatch(self, routes: Sequence[Route], not_found_message: str) -> None:
        parsed = urlparse(self.path)
        request = ApiRequest(self, parsed.path, parse_qs(parsed.query))
        if not dispatch(request, routes):
            self._send_json(
                HTTPStatus.NOT_FOUND,
                error_payload("not_found", not_found_message),
            )

    def log_message(self, format: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _require_authorized(self, *, strict: bool = False) -> bool:
        return require_authorized(self, strict=strict)

    def _authenticated_actor(self) -> str:
        return authenticated_actor(self)

    def _read_json(self) -> dict[str, Any]:
        return read_json(self)

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        send_json(self, status, payload, headers=headers)


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
