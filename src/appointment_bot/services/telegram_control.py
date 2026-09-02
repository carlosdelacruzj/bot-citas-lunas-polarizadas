from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import secrets
import signal
import time
import unicodedata
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Event, Lock, Timer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings, load_settings
from appointment_bot.core.contacts import (
    ContactValidationError,
    normalize_contact_whatsapp,
    normalize_contact_whatsapp_username,
)
from appointment_bot.core.service_packages import (
    DEFAULT_RESERVATION_PRICE_TEXT,
    SERVICE_PACKAGE_CUSTOM,
    SERVICE_PACKAGE_INTEGRAL,
    SERVICE_PACKAGE_RESTRICTED,
    SERVICE_PACKAGE_STANDARD,
    money_text,
    service_package_definition,
    service_package_label,
)
from appointment_bot.db.remote_control_audit import record_remote_control_audit
from appointment_bot.services import telegram_program_resolution
from appointment_bot.services.logger import setup_logging
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)

LIMA_TIMEZONE = ZoneInfo("America/Lima")
DEFAULT_ADMIN_API_URL = "http://127.0.0.1:8766"
DEFAULT_POLL_TIMEOUT_SECONDS = 30
RETRY_DELAY_SECONDS = 5
WORKER_MONITOR_INTERVAL_SECONDS = 300
WORKER_MONITOR_FAILURE_THRESHOLD = 3
WORKER_MONITOR_START_MINUTE = 7 * 60 + 30
WORKER_MONITOR_END_MINUTE = 18 * 60
CONFIRMATION_TTL_SECONDS = 120
CONVERSATION_TTL_SECONDS = 300
CAPTCHA_REVIEW_TTL_SECONDS = 600
NEW_CLIENT_CONVERSATION_TTL_SECONDS = 180
NEW_CLIENT_CONFIRMATION_TTL_SECONDS = 120
SENSITIVE_MESSAGE_TTL_SECONDS = 120
WORKER_COMMAND_TIMEOUT_SECONDS = 90
MAX_TELEGRAM_RESPONSE_BYTES = 1024 * 1024
CLIENTS_PAGE_SIZE = 8
GENERAL_RATE_LIMIT = 30
MUTATION_RATE_LIMIT = 15
RATE_LIMIT_WINDOW_SECONDS = 60
MUTATING_COMMANDS = {
    "captchas",
    "cliente_nuevo",
    "pausar",
    "prioridad",
    "reanudar",
    "reglas_editar",
    "reiniciar",
    "oportunidad",
    "pago",
}
ORDER_TARGET_COMMANDS = {
    "cliente",
    "prioridad",
    "pago",
    "reglas",
    "reglas_editar",
}
HELP_TEXT = """Control remoto disponible:

/pendientes [pagina] - Bandeja de usuarios que requieren seguimiento
/cola [pagina] - Usuarios que estan buscando cupo
/cobros [pagina] - Pagos pendientes
/buscar TEXTO - Buscar cliente u orden
/cliente_nuevo - Registrar manualmente un cliente
/estado - Estado y controles del sistema
/cancelar - Cancelar la operacion guiada actual
/menu - Abrir el menu principal con botones
/ayuda - Mostrar esta ayuda

Historial, errores, CAPTCHA y controles avanzados estan en Herramientas dentro de /menu.
"""


class TelegramControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramControlConfig:
    bot_token: str
    authorized_chat_ids: frozenset[str]
    admin_api_url: str
    admin_api_token: str
    offset_path: Path
    poll_timeout_seconds: int
    worker_monitor_enabled: bool
    authorized_user_ids: frozenset[str] = frozenset()


@dataclass
class WorkerHealthMonitor:
    enabled: bool
    next_check_at: float = 0.0
    consecutive_failures: int = 0
    alert_sent: bool = False
    last_failure_kind: str | None = None

    def tick(
        self,
        *,
        now: datetime,
        monotonic_now: float,
        admin_api: AdminApiClient,
        telegram: TelegramBotApi,
        chat_ids: frozenset[str],
    ) -> None:
        if not self.enabled:
            return
        minute = now.hour * 60 + now.minute
        if not WORKER_MONITOR_START_MINUTE <= minute < WORKER_MONITOR_END_MINUTE:
            self._reset()
            self.next_check_at = monotonic_now + WORKER_MONITOR_INTERVAL_SECONDS
            return
        if monotonic_now < self.next_check_at:
            return
        self.next_check_at = monotonic_now + WORKER_MONITOR_INTERVAL_SECONDS

        failure_kind = self._failure_kind(admin_api)
        if failure_kind is None:
            if self.consecutive_failures:
                logger.info(
                    "Telegram worker monitor recovered after %s failed checks.",
                    self.consecutive_failures,
                )
            self._reset()
            return

        self.consecutive_failures += 1
        self.last_failure_kind = failure_kind
        logger.warning(
            "Telegram worker monitor check failed (%s/%s): %s",
            self.consecutive_failures,
            WORKER_MONITOR_FAILURE_THRESHOLD,
            failure_kind,
        )
        if self.consecutive_failures < WORKER_MONITOR_FAILURE_THRESHOLD or self.alert_sent:
            return

        message = (
            "ALERTA OPERATIVA\n\n"
            "El worker lleva tres revisiones consecutivas sin estado saludable.\n"
            f"Causa: {failure_kind}.\n\n"
            "Accion: revisa Estado del sistema.\n"
            "No se ejecuto ningun reinicio automatico."
        )
        markup = {
            "inline_keyboard": [
                [{"text": "Estado del sistema", "callback_data": "ui:status:show"}]
            ]
        }
        try:
            for chat_id in sorted(chat_ids):
                telegram.send_message(chat_id, message, reply_markup=markup)
        except TelegramControlError as exc:
            logger.warning("Telegram worker monitor could not send alert: %s", exc)
            return
        self.alert_sent = True

    def _failure_kind(self, admin_api: AdminApiClient) -> str | None:
        try:
            payload = admin_api.get_worker()
        except TelegramControlError:
            try:
                admin_api.get_health()
            except TelegramControlError:
                return "Admin API inaccesible"
            return "consulta administrativa rechazada"
        if payload.get("worker_running") is not True:
            return "worker sin lease activo"
        logger.info("Telegram worker monitor check healthy.")
        return None

    def _reset(self) -> None:
        self.consecutive_failures = 0
        self.alert_sent = False
        self.last_failure_kind = None


@dataclass(frozen=True)
class PendingWorkerConfirmation:
    operation_id: str
    chat_id: str
    command: str
    expires_at: float
    opportunity_target: str | None = None
    expected_revision: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PendingOrderChange:
    operation_id: str
    chat_id: str
    action: str
    order_id: str
    original: dict[str, Any]
    updated: dict[str, Any]
    expires_at: float
    return_subject: str = "menu"


@dataclass
class RulesConversation:
    chat_id: str
    order_id: str
    original: dict[str, Any]
    updated: dict[str, Any]
    step: int
    expires_at: float


@dataclass
class NewClientConversation:
    chat_id: str
    session_id: str
    values: dict[str, Any]
    step: int
    expires_at: float


@dataclass(frozen=True)
class PendingClientCreation:
    operation_id: str
    chat_id: str
    values: dict[str, Any]
    expires_at: float


@dataclass
class SearchConversation:
    expires_at: float
    mode: str = "search"
    order_id: str | None = None
    return_subject: str = "menu"


@dataclass
class CaptchaReviewConversation:
    chat_id: str
    session_id: str
    expires_at: float
    item_token: str | None = None
    current_event_id: str | None = None
    current_image_sha256: str | None = None
    choice_answers: tuple[str, ...] = ()
    awaiting_manual_answer: bool = False
    skipped_event_ids: set[str] = field(default_factory=set)


class TelegramRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, chat_id: str, *, mutation: bool, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        bucket_name = "mutation" if mutation else "general"
        limit = MUTATION_RATE_LIMIT if mutation else GENERAL_RATE_LIMIT
        events = self._events[(chat_id, bucket_name)]
        cutoff = current - RATE_LIMIT_WINDOW_SECONDS
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(current)
        return True


def _callback_is_mutation(data: str) -> bool:
    if data.startswith(
        ("wc:", "oc:", "nc:", "pq:", "py:", "wk:", "op:", "cp:", "nf:", "rf:", "pr:")
    ):
        return True
    if data.startswith(("ui:manual:", "ui:captcha:", "ui:cancel:")):
        return True
    if data.startswith("om:"):
        return data.rsplit(":", maxsplit=1)[-1] in {
            "access",
            "validate",
            "editrules",
        }
    return False


def _mutation_user_authorized(
    config: TelegramControlConfig,
    chat: dict[str, Any],
    sender: Any,
) -> bool:
    if str(chat.get("type") or "") != "private" or not isinstance(sender, dict):
        return False
    chat_id = str(chat.get("id") or "")
    user_id = str(sender.get("id") or "")
    if not chat_id or not user_id:
        return False
    if config.authorized_user_ids:
        return user_id in config.authorized_user_ids
    return user_id == chat_id and chat_id in config.authorized_chat_ids


class AdminApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get_worker(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/worker")

    def get_health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def get_service_orders(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/service-orders")
        orders = payload.get("service_orders", [])
        if not isinstance(orders, list):
            raise TelegramControlError("Admin API returned an invalid service order list.")
        return [item for item in orders if isinstance(item, dict)]

    def get_operator_inbox(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/operator-inbox")

    def get_appointment_reminders(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/appointment-reminders")

    def get_service_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/service-orders/{quote(order_id, safe='')}")

    def mark_payment_paid(
        self,
        order_id: str,
        *,
        amount_paid: str,
        amount_agreed: str,
        expected_amount_paid: str,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/payment/paid",
            payload={
                "amount_paid": amount_paid,
                "amount_agreed": amount_agreed,
                "expected_payment_status": "pending",
                "expected_amount_agreed": amount_agreed,
                "expected_amount_paid": expected_amount_paid,
            },
            actor=actor,
        )

    def record_partial_payment(
        self,
        order_id: str,
        *,
        amount_paid: str,
        amount_agreed: str,
        expected_amount_paid: str,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/payment/partial",
            payload={
                "amount_paid": amount_paid,
                "amount_agreed": amount_agreed,
                "expected_payment_status": "pending",
                "expected_amount_agreed": amount_agreed,
                "expected_amount_paid": expected_amount_paid,
            },
            actor=actor,
        )

    def search_service_orders(self, query: str) -> list[dict[str, Any]]:
        payload = self._request(
            "POST", "/api/v1/service-orders/search", payload={"query": query}
        )
        orders = payload.get("service_orders", [])
        if not isinstance(orders, list):
            raise TelegramControlError("Admin API returned an invalid search result.")
        return [item for item in orders if isinstance(item, dict)]

    def get_service_order_credentials(self, order_id: str) -> dict[str, Any]:
        return self._request(
            "GET", f"/api/v1/service-orders/{quote(order_id, safe='')}/credentials"
        )

    def update_service_order_credentials(
        self,
        order_id: str,
        *,
        document_number: str,
        document_type: str,
        password: str,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/credentials",
            payload={
                "document_number": document_number,
                "document_type": document_type,
                "password": password,
            },
            actor=actor,
        )

    def create_service_order(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/service-orders",
            payload=values,
            actor=actor,
            request_timeout=15,
        )

    def get_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/v1/runs?limit={limit}")
        runs = payload.get("runs", [])
        if not isinstance(runs, list):
            raise TelegramControlError("Admin API returned an invalid run list.")
        return [item for item in runs if isinstance(item, dict)]

    def get_captcha_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/captcha-shadow/summary")

    def get_pending_captcha_events(
        self,
        *,
        page: int = 1,
        targeted: bool = True,
    ) -> dict[str, Any]:
        query = urlencode(
            {
                "page": page,
                "page_size": 48,
                "review_status": "pending",
                "review_scope": "targeted" if targeted else "all",
                "sort": "review_priority" if targeted else "oldest",
            }
        )
        return self._request("GET", f"/api/v1/captcha-shadow/events?{query}")

    def get_captcha_image(self, event_id: str) -> tuple[bytes, str]:
        return self._request_bytes(
            "GET",
            f"/api/v1/captcha-shadow/events/{quote(event_id, safe='')}/image",
        )

    def save_captcha_human_label(
        self,
        event_id: str,
        answer: str,
        image_sha256: str,
        *,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/captcha-shadow/events/{quote(event_id, safe='')}/human-label",
            payload={
                "answer": answer,
                "expected_image_sha256": image_sha256,
                "expected_unlabeled": True,
                "note": "Validated from Telegram review queue.",
            },
            actor=actor,
        )

    def update_order_priority(
        self,
        order_id: str,
        priority: int,
        *,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/priority",
            payload={"priority": priority},
            actor=actor,
        )

    def update_order_rules(
        self,
        order_id: str,
        rules: dict[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/restrictions",
            payload=rules,
            actor=actor,
        )

    def revalidate_service_order(self, order_id: str, *, actor: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/validate",
            payload={},
            actor=actor,
        )

    def resolve_service_order_programs(
        self,
        order_id: str,
        resolution: dict[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/program-resolution",
            payload=resolution,
            actor=actor,
        )

    def enqueue_worker_command(self, command: str, *, actor: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/worker/{command}",
            payload={},
            actor=actor,
        )

    def get_worker_command(self, command_id: str) -> dict[str, Any] | None:
        payload = self._request("GET", "/api/v1/worker/commands?limit=100")
        commands = payload.get("commands", [])
        if not isinstance(commands, list):
            raise TelegramControlError("Admin API returned an invalid command list.")
        return next(
            (
                item
                for item in commands
                if isinstance(item, dict) and item.get("command_id") == command_id
            ),
            None,
        )

    def get_opportunity_control(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/runtime-controls/opportunity")

    def update_opportunity_control(
        self,
        *,
        action: str,
        target: str,
        reason: str,
        expected_revision: int,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/runtime-controls/opportunity",
            payload={
                "action": action,
                "target": target,
                "reason": reason,
                "expected_revision": expected_revision,
            },
            actor=actor,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        actor: str | None = None,
        request_timeout: int = 5,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if actor:
            headers["X-Appointment-Actor"] = actor
            headers["X-Appointment-Actor-Signature"] = hmac.new(
                self.token.encode("utf-8"),
                actor.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=request_timeout) as response:
                return _read_json_response(response)
        except HTTPError as exc:
            raise TelegramControlError(
                f"Admin API rejected the action with HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise TelegramControlError("Admin API is not reachable.") from exc

    def _request_bytes(self, method: str, path: str) -> tuple[bytes, str]:
        request = Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            method=method,
        )
        try:
            with urlopen(request, timeout=5) as response:
                content_type = response.headers.get_content_type()
                return response.read(MAX_TELEGRAM_RESPONSE_BYTES + 1), content_type
        except HTTPError as exc:
            raise TelegramControlError(
                f"Admin API rejected the action with HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise TelegramControlError("Admin API is not reachable.") from exc


class TelegramBotApi:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def get_me(self) -> dict[str, Any]:
        return self._request("getMe")

    def get_webhook_info(self) -> dict[str, Any]:
        return self._request("getWebhookInfo")

    def get_updates(self, *, offset: int | None, timeout_seconds: int) -> list[dict[str, Any]]:
        payload: dict[str, str] = {
            "timeout": str(timeout_seconds),
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }
        if offset is not None:
            payload["offset"] = str(offset)
        data = self._request("getUpdates", payload, request_timeout=timeout_seconds + 10)
        result = data.get("result", [])
        if not isinstance(result, list):
            raise TelegramControlError("Telegram returned an invalid updates list.")
        return [item for item in result if isinstance(item, dict)]

    def set_operator_commands(self) -> None:
        commands = [
            {"command": "menu", "description": "Abrir el menu principal"},
            {"command": "pendientes", "description": "Ver casos que requieren atencion"},
            {"command": "cola", "description": "Ver clientes buscando cupo"},
            {"command": "cobros", "description": "Ver pagos pendientes"},
            {"command": "buscar", "description": "Buscar cliente u orden"},
            {"command": "cliente_nuevo", "description": "Registrar un cliente"},
            {"command": "estado", "description": "Ver estado y controles"},
            {"command": "cancelar", "description": "Cancelar la operacion guiada"},
            {"command": "ayuda", "description": "Ver ayuda"},
        ]
        self._request(
            "setMyCommands",
            {
                "commands": json.dumps(commands),
                "scope": json.dumps({"type": "all_private_chats"}),
            },
        )

    def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        return self._request(
            "sendMessage",
            payload,
        )

    def send_photo(
        self,
        chat_id: str,
        photo: bytes,
        filename: str,
        caption: str,
        *,
        content_type: str = "image/png",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        boundary = f"----appointment-bot-{secrets.token_hex(12)}"
        fields = {"chat_id": chat_id, "caption": caption}
        if reply_markup is not None:
            fields["reply_markup"] = json.dumps(reply_markup)
        body = _multipart_form_data(
            boundary,
            fields=fields,
            files={"photo": (filename, content_type, photo)},
        )
        request = Request(
            f"{self.base_url}/sendPhoto",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                data = _read_json_response(response)
        except HTTPError as exc:
            raise TelegramControlError(
                f"Telegram sendPhoto failed with HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise TelegramControlError("Telegram sendPhoto is not reachable.") from exc
        if not data.get("ok"):
            raise TelegramControlError("Telegram rejected sendPhoto.")
        return data

    def delete_message(self, chat_id: str, message_id: int) -> None:
        self._request(
            "deleteMessage",
            {"chat_id": chat_id, "message_id": str(message_id)},
        )

    def clear_inline_keyboard(self, chat_id: str, message_id: int) -> None:
        self._request(
            "editMessageReplyMarkup",
            {
                "chat_id": chat_id,
                "message_id": str(message_id),
                "reply_markup": json.dumps({"inline_keyboard": []}),
            },
        )

    def answer_callback_query(self, callback_query_id: str, text: str) -> None:
        self._request(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text},
        )

    def _request(
        self,
        method: str,
        payload: dict[str, str] | None = None,
        *,
        request_timeout: int = 15,
    ) -> dict[str, Any]:
        body = urlencode(payload).encode("utf-8") if payload is not None else None
        request = Request(f"{self.base_url}/{method}", data=body, method="POST")
        try:
            with urlopen(request, timeout=request_timeout) as response:
                data = _read_json_response(response)
        except HTTPError as exc:
            raise TelegramControlError(f"Telegram {method} failed with HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            raise TelegramControlError(f"Telegram {method} is not reachable.") from exc
        if not data.get("ok"):
            raise TelegramControlError(f"Telegram rejected {method}.")
        return data


def load_control_config(settings: Settings) -> TelegramControlConfig:
    if not settings.telegram_enabled:
        raise TelegramControlError("Telegram is disabled.")
    chat_ids_text = os.getenv("TELEGRAM_CONTROL_CHAT_IDS", "").strip()
    chat_ids = {
        item.strip()
        for item in (chat_ids_text.split(",") if chat_ids_text else [settings.telegram_chat_id])
        if item.strip()
    }
    if not chat_ids:
        raise TelegramControlError("No authorized Telegram chat_id is configured.")
    user_ids = frozenset(
        item.strip()
        for item in os.getenv("TELEGRAM_CONTROL_USER_IDS", "").split(",")
        if item.strip()
    )
    admin_api_token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
    if not admin_api_token:
        raise TelegramControlError("APPOINTMENT_BOT_API_TOKEN is required.")
    workdir = Path(os.getenv("APPOINTMENT_BOT_WORKDIR", "").strip() or Path.cwd())
    offset_text = os.getenv("TELEGRAM_CONTROL_OFFSET_PATH", "").strip()
    offset_path = (
        Path(offset_text) if offset_text else workdir / ".runtime/telegram-control-offset.json"
    )
    poll_timeout = _positive_int(
        os.getenv("TELEGRAM_CONTROL_POLL_TIMEOUT_SECONDS"),
        default=DEFAULT_POLL_TIMEOUT_SECONDS,
    )
    return TelegramControlConfig(
        bot_token=settings.telegram_bot_token,
        authorized_chat_ids=frozenset(chat_ids),
        authorized_user_ids=user_ids,
        admin_api_url=_validated_admin_api_url(
            os.getenv("TELEGRAM_CONTROL_ADMIN_API_URL", DEFAULT_ADMIN_API_URL)
        ),
        admin_api_token=admin_api_token,
        offset_path=offset_path,
        poll_timeout_seconds=poll_timeout,
        worker_monitor_enabled=os.getenv(
            "TELEGRAM_WORKER_MONITOR_ENABLED",
            "false",
        ).strip().lower()
        in {"1", "true", "yes", "on"},
    )


def _validated_admin_api_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.username or parsed.password or not parsed.hostname:
        raise TelegramControlError("TELEGRAM_CONTROL_ADMIN_API_URL is invalid.")
    loopback = parsed.hostname.lower() in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme == "http" and loopback:
        return normalized
    if parsed.scheme == "https":
        return normalized
    raise TelegramControlError(
        "TELEGRAM_CONTROL_ADMIN_API_URL must use loopback HTTP or HTTPS."
    )


def run_control(*, check_only: bool = False) -> int:
    settings = load_settings(require_login=False)
    setup_logging(settings)
    config = load_control_config(settings)
    telegram = TelegramBotApi(config.bot_token)
    admin_api = AdminApiClient(config.admin_api_url, config.admin_api_token)
    identity = telegram.get_me().get("result", {})
    webhook = telegram.get_webhook_info().get("result", {})
    if webhook.get("url"):
        raise TelegramControlError("Telegram has a webhook configured; long polling cannot start.")
    worker = admin_api.get_worker()
    logger.info(
        "Telegram control validated for bot_id=%s, authorized_chats=%s, worker_phase=%s",
        identity.get("id"),
        len(config.authorized_chat_ids),
        worker.get("phase"),
    )
    if check_only:
        return 0

    stop_event = Event()
    _install_signal_handlers(stop_event)
    next_offset = _load_next_offset(config.offset_path)
    pending_confirmations: dict[str, PendingWorkerConfirmation] = {}
    pending_order_changes: dict[str, PendingOrderChange] = {}
    rules_conversations: dict[str, RulesConversation] = {}
    new_client_conversations: dict[str, NewClientConversation] = {}
    pending_client_creations: dict[str, PendingClientCreation] = {}
    search_conversations: dict[str, SearchConversation] = {}
    captcha_conversations: dict[str, CaptchaReviewConversation] = {}
    recent_orders: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=8))
    rate_limiter = TelegramRateLimiter()
    worker_monitor = WorkerHealthMonitor(enabled=config.worker_monitor_enabled)
    confirmation_lock = Lock()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="telegram-worker-command")
    telegram.set_operator_commands()
    _record_audit_safe(actor="telegram-control", action="receiver", status="started")
    logger.info("Telegram control long polling started.")
    try:
        while not stop_event.is_set():
            try:
                worker_monitor.tick(
                    now=datetime.now(LIMA_TIMEZONE),
                    monotonic_now=time.monotonic(),
                    admin_api=admin_api,
                    telegram=telegram,
                    chat_ids=config.authorized_chat_ids,
                )
                updates = telegram.get_updates(
                    offset=next_offset,
                    timeout_seconds=config.poll_timeout_seconds,
                )
                _remove_expired_confirmations(pending_confirmations, confirmation_lock)
                _remove_expired_order_state(
                    pending_order_changes,
                    rules_conversations,
                    confirmation_lock,
                )
                for update in updates:
                    update_id = _update_id(update)
                    if update_id is None:
                        continue
                    _process_update(
                        update,
                        config,
                        telegram,
                        admin_api,
                        pending_confirmations=pending_confirmations,
                        pending_order_changes=pending_order_changes,
                        rules_conversations=rules_conversations,
                        new_client_conversations=new_client_conversations,
                        pending_client_creations=pending_client_creations,
                        search_conversations=search_conversations,
                        captcha_conversations=captcha_conversations,
                        recent_orders=recent_orders,
                        rate_limiter=rate_limiter,
                        confirmation_lock=confirmation_lock,
                        executor=executor,
                    )
                    next_offset = update_id + 1
                    _store_next_offset(config.offset_path, next_offset)
                _remove_expired_client_state(
                    new_client_conversations,
                    pending_client_creations,
                    telegram,
                    confirmation_lock,
                )
                _remove_expired_captcha_state(captcha_conversations, telegram)
            except TelegramControlError as exc:
                logger.warning("Telegram control polling failed: %s", exc)
                stop_event.wait(RETRY_DELAY_SECONDS)
            except Exception:
                logger.exception("Unexpected Telegram control polling failure")
                stop_event.wait(RETRY_DELAY_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    logger.info("Telegram control stopped.")
    return 0


def _process_update(
    update: dict[str, Any],
    config: TelegramControlConfig,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    *,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
    new_client_conversations: dict[str, NewClientConversation],
    pending_client_creations: dict[str, PendingClientCreation],
    search_conversations: dict[str, SearchConversation],
    captcha_conversations: dict[str, CaptchaReviewConversation],
    recent_orders: dict[str, deque[str]],
    rate_limiter: TelegramRateLimiter,
    confirmation_lock: Lock,
    executor: ThreadPoolExecutor,
) -> None:
    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        _process_callback_query(
            callback_query,
            config,
            telegram,
            admin_api,
            pending_confirmations,
            pending_order_changes,
            pending_client_creations,
            new_client_conversations,
            rules_conversations,
            search_conversations,
            captcha_conversations,
            recent_orders,
            rate_limiter,
            confirmation_lock,
            executor,
        )
        return
    message = update.get("message")
    if not isinstance(message, dict):
        return
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return
    chat_id = str(chat["id"])
    sender = message.get("from")
    user_id = str(sender.get("id") or "") if isinstance(sender, dict) else ""
    if chat_id not in config.authorized_chat_ids:
        logger.warning("Ignored Telegram update from an unauthorized chat.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="message", status="denied"
        )
        return
    text = message.get("text")
    if not isinstance(text, str):
        return
    if not text.strip().startswith("/"):
        active_search = search_conversations.get(chat_id)
        guided_mutation = (
            chat_id in captcha_conversations
            or chat_id in new_client_conversations
            or chat_id in rules_conversations
            or (
                active_search is not None
                and active_search.mode in {"credentials", "payment"}
            )
        )
        if not rate_limiter.allow(chat_id, mutation=guided_mutation):
            _record_audit_safe(
                actor=_telegram_actor(chat_id),
                action="conversation_reply",
                status="rate_limited",
            )
            telegram.send_message(
                chat_id,
                "Estas respondiendo demasiado rapido. Espera un minuto para continuar.",
            )
            return
        search = search_conversations.get(chat_id)
        if chat_id in captcha_conversations and not _mutation_user_authorized(
            config, chat, sender
        ):
            telegram.send_message(
                chat_id,
                "El etiquetado solo se permite al operador autorizado en chat privado.",
            )
            return
        if _process_captcha_review_message(
            chat_id,
            text,
            telegram,
            admin_api,
            captcha_conversations,
        ):
            return
        if search is not None:
            if search.expires_at <= time.monotonic():
                search_conversations.pop(chat_id, None)
                telegram.send_message(
                    chat_id,
                    (
                        "La correccion de acceso vencio. Abre nuevamente el cliente."
                        if search.mode == "credentials"
                        else "El registro del abono vencio. Abre nuevamente el cobro."
                        if search.mode == "payment"
                        else "La busqueda vencio. Pulsa Buscar para intentar otra vez."
                    ),
                )
                return
            if search.mode == "credentials" and search.order_id:
                if not _mutation_user_authorized(config, chat, sender):
                    telegram.send_message(
                        chat_id,
                        "La contrasena solo se puede corregir por el operador autorizado "
                        "desde un chat privado.",
                    )
                    return
                if not 1 <= len(text) <= 200:
                    search.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
                    telegram.send_message(
                        chat_id,
                        "La contrasena debe tener entre 1 y 200 caracteres. Intenta otra vez.",
                    )
                    _delete_message_safe(telegram, chat_id, message.get("message_id"))
                    return
                search_conversations.pop(chat_id, None)
                try:
                    _request_credentials_change(
                        chat_id,
                        search.order_id,
                        text,
                        telegram,
                        admin_api,
                        pending_order_changes,
                        confirmation_lock,
                        return_subject=search.return_subject,
                    )
                finally:
                    _delete_message_safe(telegram, chat_id, message.get("message_id"))
                return
            if search.mode == "payment" and search.order_id:
                search_conversations.pop(chat_id, None)
                _request_payment_change(
                    chat_id,
                    f"{search.order_id} {text}",
                    telegram,
                    admin_api,
                    pending_order_changes,
                    confirmation_lock,
                    return_subject=search.return_subject,
                )
                return
            search_conversations.pop(chat_id, None)
            _send_search_results(chat_id, text, telegram, admin_api)
            return
        new_client = new_client_conversations.get(chat_id)
        password_message = new_client is not None and new_client.step == 2
        if _process_new_client_message(
            chat_id,
            text,
            telegram,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        ):
            if password_message:
                message_id = message.get("message_id")
                if isinstance(message_id, int):
                    try:
                        telegram.delete_message(chat_id, message_id)
                    except TelegramControlError:
                        logger.warning("Could not delete Telegram password input message.")
            return
        if _process_rules_conversation_message(
            chat_id,
            text,
            telegram,
            rules_conversations,
            pending_order_changes,
            confirmation_lock,
        ):
            return
    command, arguments = _command_parts(text)
    if command is None:
        telegram.send_message(
            chat_id,
            "No entendi ese mensaje. Usa /menu para elegir una opcion o /buscar TEXTO.",
            reply_markup=_main_menu_markup(),
        )
        return
    mutation = command in MUTATING_COMMANDS
    if mutation and not _mutation_user_authorized(config, chat, sender):
        _record_audit_safe(
            actor=_telegram_actor(chat_id, user_id),
            action=command,
            status="denied",
            detail="Mutation requires an authorized user in a private chat.",
        )
        telegram.send_message(
            chat_id,
            "Por seguridad, esta accion solo se permite al operador autorizado "
            "desde un chat privado.",
        )
        return
    if not rate_limiter.allow(chat_id, mutation=mutation):
        _record_audit_safe(
            actor=_telegram_actor(chat_id),
            action=command,
            status="rate_limited",
            target_id=(
                _audit_target(arguments) if command in ORDER_TARGET_COMMANDS else None
            ),
        )
        telegram.send_message(
            chat_id,
            "Recibi demasiadas solicitudes seguidas. Espera un minuto y vuelve a intentar.",
        )
        return
    audit_target = _audit_target(arguments) if command in ORDER_TARGET_COMMANDS else None
    _record_audit_safe(
        actor=_telegram_actor(chat_id, user_id),
        action=command,
        status="accepted",
        target_type="service_order" if audit_target else None,
        target_id=audit_target,
    )
    if command in {"menu", "start"}:
        _send_main_menu(chat_id, telegram, admin_api)
        return
    if command in {"ayuda", "help"}:
        telegram.send_message(chat_id, HELP_TEXT, reply_markup=_main_menu_markup())
        return
    if command == "cancelar":
        removed = _cancel_chat_confirmations(chat_id, pending_confirmations, confirmation_lock)
        order_removed = _cancel_chat_order_state(
            chat_id,
            pending_order_changes,
            rules_conversations,
            confirmation_lock,
        )
        with confirmation_lock:
            client_removed = new_client_conversations.pop(chat_id, None) is not None
            client_removed = _cancel_pending_client_creation_unlocked(
                chat_id, pending_client_creations
            ) or client_removed
            search_removed = search_conversations.pop(chat_id, None) is not None
            captcha_removed = captcha_conversations.pop(chat_id, None) is not None
        response = (
            "Operacion pendiente cancelada."
            if removed
            or order_removed
            or client_removed
            or search_removed
            or captcha_removed
            else "No hay una operacion guiada activa."
        )
        telegram.send_message(chat_id, response)
        return
    if command == "estado":
        _send_worker_panel(chat_id, telegram, admin_api)
        return
    if command == "oportunidad":
        if arguments:
            telegram.send_message(chat_id, "Uso: /oportunidad")
            return
        _send_opportunity_panel(chat_id, telegram, admin_api)
        return
    if command == "clientes":
        _send_clients(chat_id, arguments, telegram, admin_api)
        return
    if command == "pendientes":
        _send_pending_attention(chat_id, arguments, telegram, admin_api)
        return
    if command == "cola":
        _send_queue(chat_id, arguments, telegram, admin_api)
        return
    if command == "cobros":
        _send_pending_payments(chat_id, arguments, telegram, admin_api)
        return
    if command == "buscar":
        _send_search_results(chat_id, arguments, telegram, admin_api)
        return
    if command == "resumen":
        _send_daily_summary(chat_id, telegram, admin_api)
        return
    if command == "captchas":
        try:
            captcha_enabled = bool(admin_api.get_health().get("captcha_shadow_enabled"))
        except TelegramControlError:
            captcha_enabled = False
        if not captcha_enabled:
            telegram.send_message(
                chat_id,
                "El etiquetado CAPTCHA no esta activo en este momento.",
                reply_markup=_main_menu_markup(),
            )
            return
        search_conversations.pop(chat_id, None)
        _cancel_chat_client_state(
            chat_id,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        _cancel_chat_order_state(
            chat_id,
            pending_order_changes,
            rules_conversations,
            confirmation_lock,
        )
        _start_captcha_review(chat_id, telegram, admin_api, captcha_conversations)
        return
    if command in {"cliente", "reglas"}:
        _send_order_query(chat_id, command, arguments, telegram, admin_api)
        return
    if command == "cliente_nuevo":
        search_conversations.pop(chat_id, None)
        captcha_conversations.pop(chat_id, None)
        _cancel_chat_order_state(
            chat_id,
            pending_order_changes,
            rules_conversations,
            confirmation_lock,
        )
        _start_new_client_conversation(
            chat_id,
            arguments,
            telegram,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        return
    if command == "prioridad":
        _request_priority_change(
            chat_id,
            arguments,
            telegram,
            admin_api,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "pago":
        _request_payment_change(
            chat_id,
            arguments,
            telegram,
            admin_api,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "reglas_editar":
        search_conversations.pop(chat_id, None)
        captcha_conversations.pop(chat_id, None)
        _cancel_chat_client_state(
            chat_id,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        _start_rules_conversation(
            chat_id,
            arguments,
            telegram,
            admin_api,
            rules_conversations,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "ultimos_errores":
        _send_recent_errors(chat_id, telegram, admin_api)
        return
    if command in {"pausar", "reanudar", "reiniciar"}:
        if arguments:
            telegram.send_message(chat_id, f"Uso: /{command}")
            return
        worker_command = {
            "pausar": "pause",
            "reanudar": "resume",
            "reiniciar": "restart",
        }[command]
        _request_worker_confirmation(
            chat_id,
            worker_command,
            telegram,
            pending_confirmations,
            confirmation_lock,
        )
        return
    telegram.send_message(chat_id, "Comando no reconocido. Usa /ayuda.")


def _main_menu_markup(counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = counts or {}
    pending_label = "Pendientes"
    queue_label = "Buscando cupo"
    payments_label = "Por cobrar"
    if "pending" in counts:
        pending_label += f" · {counts['pending']}"
    if "queue" in counts:
        queue_label += f" · {counts['queue']}"
    if "payments" in counts:
        payments_label += f" · {counts['payments']}"
    return {
        "inline_keyboard": [
            [
                {"text": pending_label, "callback_data": "ui:pending:1"},
                {"text": queue_label, "callback_data": "ui:queue:1"},
            ],
            [
                {"text": payments_label, "callback_data": "ui:payments:1"},
                {"text": "Nuevo cliente", "callback_data": "ui:manual:start"},
            ],
            [
                {"text": "Buscar", "callback_data": "ui:search:start"},
                {"text": "Citas y resumen", "callback_data": "ui:summary:show"},
            ],
            [
                {"text": "Estado", "callback_data": "ui:status:show"},
                {"text": "Herramientas", "callback_data": "ui:tools:show"},
            ],
        ]
    }


def _send_main_menu(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    counts: dict[str, int] = {}
    try:
        inbox = admin_api.get_operator_inbox()
        summary = inbox.get("summary")
        if isinstance(summary, dict):
            counts["pending"] = int(summary.get("total") or 0)
        orders = admin_api.get_service_orders()
        counts["queue"] = sum(str(order.get("status") or "") == "ready" for order in orders)
        counts["payments"] = sum(
            str(order.get("reservation_status") or "") == "confirmed"
            and str(order.get("payment_status") or "") == "pending"
            for order in orders
        )
    except (TelegramControlError, TypeError, ValueError):
        counts = {}
    telegram.send_message(
        chat_id,
        "OPERACION DIARIA\n\nElige que deseas revisar o hacer.",
        reply_markup=_main_menu_markup(counts),
    )


def _send_tools_menu(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    rows = [
        [{"text": "Historial de clientes", "callback_data": "ui:clients:1"}],
        [{"text": "Oportunidades", "callback_data": "ui:opportunity:show"}],
        [{"text": "Errores recientes", "callback_data": "ui:errors:show"}],
    ]
    try:
        captcha_enabled = bool(admin_api.get_health().get("captcha_shadow_enabled"))
    except TelegramControlError:
        captcha_enabled = False
    if captcha_enabled:
        rows.insert(
            1,
            [{"text": "Etiquetar CAPTCHA", "callback_data": "ui:captcha:start"}],
        )
    rows.append([{"text": "Volver", "callback_data": "ui:menu:main"}])
    telegram.send_message(
        chat_id,
        "HERRAMIENTAS\n\nFunciones de revision y control menos frecuentes.",
        reply_markup={"inline_keyboard": rows},
    )


def _start_captcha_review(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> None:
    conversations[chat_id] = CaptchaReviewConversation(
        chat_id=chat_id,
        session_id=secrets.token_hex(4),
        expires_at=time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS,
    )
    _send_next_captcha_review(chat_id, telegram, admin_api, conversations)


def _send_next_captcha_review(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> None:
    conversation = conversations.get(chat_id)
    if conversation is None or conversation.expires_at <= time.monotonic():
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "La sesion de CAPTCHA vencio por inactividad. Abrela nuevamente desde el menu.",
            reply_markup=_main_menu_markup(),
        )
        return
    try:
        event, pending = _next_pending_captcha(admin_api, conversation.skipped_event_ids)
        summary = admin_api.get_captcha_summary()
    except TelegramControlError as exc:
        logger.warning("Could not load Telegram CAPTCHA review queue: %s", exc)
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "No pude abrir la cola de CAPTCHA. Verifica el servicio sombra e intenta otra vez.",
            reply_markup=_main_menu_markup(),
        )
        return
    if event is None:
        conversations.pop(chat_id, None)
        if pending == 0:
            message = (
                "REVISION PRIORITARIA COMPLETA\n\n"
                "No quedan CAPTCHA del canario V6, anomalias, desacuerdos ni "
                "muestras de control pendientes. El resto permanece guardado en Historial."
            )
        else:
            message = (
                "No quedan CAPTCHA sin revisar en esta sesion.\n\n"
                f"Omitiste {len(conversation.skipped_event_ids)}. "
                "Vuelve a entrar para verlos otra vez."
            )
        telegram.send_message(chat_id, message, reply_markup=_main_menu_markup())
        return
    event_id = str(event.get("event_id") or "")
    image_sha256 = str(event.get("image_sha256") or "")
    if not event_id or len(image_sha256) != 64:
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "La cola devolvio un CAPTCHA incompleto. Intenta nuevamente mas tarde.",
            reply_markup=_main_menu_markup(),
        )
        return
    choices = _captcha_prediction_choices(event)
    try:
        image, content_type = admin_api.get_captcha_image(event_id)
    except TelegramControlError as exc:
        logger.warning("Could not load Telegram CAPTCHA image event_id=%s error=%s", event_id, exc)
        conversation.skipped_event_ids.add(event_id)
        telegram.send_message(chat_id, "No pude abrir esa imagen; pase al siguiente CAPTCHA.")
        _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
        return
    if len(image) > MAX_TELEGRAM_RESPONSE_BYTES:
        conversation.skipped_event_ids.add(event_id)
        telegram.send_message(
            chat_id,
            "La imagen excede el limite permitido; pase al siguiente CAPTCHA.",
        )
        _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
        return
    conversation.item_token = secrets.token_hex(3)
    conversation.current_event_id = event_id
    conversation.current_image_sha256 = image_sha256
    conversation.choice_answers = tuple(answer for answer, _models in choices)
    conversation.awaiting_manual_answer = False
    conversation.expires_at = time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS
    stats = summary.get("stats") if isinstance(summary.get("stats"), dict) else {}
    total = max(0, int(stats.get("events") or 0))
    labeled = max(0, int(stats.get("human_labeled") or 0))
    caption = (
        "ETIQUETAR CAPTCHA PRIORITARIO\n\n"
        f"Motivo: {_captcha_review_reason(event)}\n"
        f"Validados: {labeled}/{total} | Prioritarios: {pending}\n"
        "Elige una respuesta de los modelos o escribe la tuya.\n"
        "La sesion vence despues de 10 minutos sin actividad."
    )
    telegram.send_photo(
        chat_id,
        image,
        f"captcha-{event_id[:12]}.png",
        caption,
        content_type=content_type or mimetypes.types_map.get(".png", "image/png"),
        reply_markup=_captcha_review_markup(conversation, choices),
    )


def _captcha_review_reason(event: dict[str, Any]) -> str:
    return {
        "canary_v6": "decision del canario V6",
        "anomaly": "anomalia o baja confianza",
        "model_disagreement": "desacuerdo V3/V6",
        "control_sample": "muestra aleatoria de control",
    }.get(str(event.get("review_priority_reason") or ""), "revision dirigida")


def _next_pending_captcha(
    admin_api: AdminApiClient,
    skipped_event_ids: set[str],
) -> tuple[dict[str, Any] | None, int]:
    page = 1
    pending = 0
    while True:
        payload = admin_api.get_pending_captcha_events(page=page)
        events = payload.get("events")
        pagination = payload.get("pagination")
        if not isinstance(events, list) or not isinstance(pagination, dict):
            raise TelegramControlError("Admin API returned an invalid CAPTCHA queue.")
        pending = max(0, int(pagination.get("total") or 0))
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("event_id") or "")
            if event_id and event_id not in skipped_event_ids:
                return event, pending
        if page >= max(1, int(pagination.get("total_pages") or 1)):
            return None, pending
        page += 1


def _captcha_prediction_choices(
    event: dict[str, Any],
) -> list[tuple[str, tuple[str, ...]]]:
    predictions = event.get("predictions")
    if not isinstance(predictions, list):
        return []
    selected_model = str(event.get("selected_model_name") or "")
    ordered = sorted(
        (item for item in predictions if isinstance(item, dict)),
        key=lambda item: str(item.get("model_name") or "") != selected_model,
    )
    grouped: dict[str, list[str]] = {}
    for prediction in ordered:
        answer = str(prediction.get("prediction") or "").strip().upper()
        if re.fullmatch(r"[A-Z0-9]{5}", answer) is None:
            continue
        model = _captcha_model_short_label(str(prediction.get("model_name") or "modelo"))
        models = grouped.setdefault(answer, [])
        if model not in models:
            models.append(model)
    return [(answer, tuple(models)) for answer, models in grouped.items()]


def _captcha_model_short_label(model_name: str) -> str:
    return {
        "v1_real": "v1",
        "v2_scratch": "v2 scratch",
        "v2_selected": "v2",
        "v3_selected": "v3",
        "v4_candidate": "v4",
        "v5_candidate": "v5",
        "v6_sequence_candidate": "v6",
    }.get(model_name, model_name[:16])


def _captcha_review_markup(
    conversation: CaptchaReviewConversation,
    choices: list[tuple[str, tuple[str, ...]]],
) -> dict[str, Any]:
    prefix = f"cp:{conversation.session_id}:{conversation.item_token}:"
    rows = [
        [{
            "text": f"{answer} - {' + '.join(models)}"[:60],
            "callback_data": f"{prefix}a{index}",
        }]
        for index, (answer, models) in enumerate(choices)
    ]
    rows.extend(
        [
            [{"text": "Escribir otra respuesta", "callback_data": f"{prefix}manual"}],
            [
                {"text": "Omitir", "callback_data": f"{prefix}skip"},
                {"text": "Salir", "callback_data": f"{prefix}exit"},
            ],
        ]
    )
    return {"inline_keyboard": rows}


def _process_captcha_review_message(
    chat_id: str,
    text: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> bool:
    conversation = conversations.get(chat_id)
    if conversation is None:
        return False
    if conversation.expires_at <= time.monotonic():
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "La sesion de CAPTCHA vencio por inactividad. La respuesta no fue guardada.",
            reply_markup=_main_menu_markup(),
        )
        return True
    if not conversation.awaiting_manual_answer:
        telegram.send_message(
            chat_id,
            "Usa uno de los botones del CAPTCHA o pulsa Escribir otra respuesta.",
        )
        return True
    answer = text.strip().upper()
    if re.fullmatch(r"[A-Z0-9]{5}", answer) is None:
        conversation.expires_at = time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS
        telegram.send_message(
            chat_id,
            "Respuesta invalida. Envia exactamente 5 letras o numeros, sin espacios.",
        )
        return True
    if _save_captcha_review_answer(chat_id, answer, telegram, admin_api, conversations):
        telegram.send_message(chat_id, f"Guardado: {answer}. Abriendo el siguiente CAPTCHA...")
        _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
    return True


def _process_captcha_review_callback(
    callback_id: str,
    data: str,
    message: Any,
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> bool:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "cp":
        return False
    _prefix, session_id, item_token, action = parts
    conversation = conversations.get(chat_id)
    if conversation is None or conversation.expires_at <= time.monotonic():
        conversations.pop(chat_id, None)
        telegram.answer_callback_query(callback_id, "La sesion ya vencio.")
        return True
    if conversation.session_id != session_id or conversation.item_token != item_token:
        telegram.answer_callback_query(
            callback_id,
            "Ese boton ya no corresponde al CAPTCHA actual.",
        )
        return True
    conversation.expires_at = time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS
    if action == "manual":
        _clear_captcha_review_buttons(chat_id, message, telegram)
        conversation.awaiting_manual_answer = True
        telegram.answer_callback_query(callback_id, "Escribe los 5 caracteres.")
        telegram.send_message(
            chat_id,
            "Escribe la respuesta correcta con exactamente 5 letras o numeros. "
            "Usa /cancelar para salir.",
        )
        return True
    if action == "skip":
        _clear_captcha_review_buttons(chat_id, message, telegram)
        if conversation.current_event_id:
            conversation.skipped_event_ids.add(conversation.current_event_id)
        telegram.answer_callback_query(callback_id, "CAPTCHA omitido en esta sesion.")
        _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
        return True
    if action == "exit":
        _clear_captcha_review_buttons(chat_id, message, telegram)
        conversations.pop(chat_id, None)
        telegram.answer_callback_query(callback_id, "Etiquetado pausado.")
        telegram.send_message(
            chat_id,
            "Etiquetado pausado. Las respuestas guardadas se conservaron.",
            reply_markup=_main_menu_markup(),
        )
        return True
    if not action.startswith("a") or not action[1:].isdigit():
        telegram.answer_callback_query(callback_id, "Accion de CAPTCHA no reconocida.")
        return True
    choice_index = int(action[1:])
    if choice_index >= len(conversation.choice_answers):
        telegram.answer_callback_query(callback_id, "La respuesta elegida ya no esta disponible.")
        return True
    answer = conversation.choice_answers[choice_index]
    if not _save_captcha_review_answer(chat_id, answer, telegram, admin_api, conversations):
        telegram.answer_callback_query(callback_id, "No se pudo guardar.")
        return True
    _clear_captcha_review_buttons(chat_id, message, telegram)
    telegram.answer_callback_query(callback_id, f"Guardado: {answer}")
    _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
    return True


def _clear_captcha_review_buttons(
    chat_id: str,
    message: Any,
    telegram: TelegramBotApi,
) -> None:
    message_id = message.get("message_id") if isinstance(message, dict) else None
    if not isinstance(message_id, int):
        return
    try:
        telegram.clear_inline_keyboard(chat_id, message_id)
    except TelegramControlError:
        logger.warning("Could not clear stale CAPTCHA review buttons message_id=%s", message_id)


def _save_captcha_review_answer(
    chat_id: str,
    answer: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> bool:
    conversation = conversations.get(chat_id)
    if (
        conversation is None
        or conversation.current_event_id is None
        or conversation.current_image_sha256 is None
    ):
        telegram.send_message(chat_id, "El CAPTCHA actual ya no esta disponible.")
        return False
    event_id = conversation.current_event_id
    try:
        admin_api.save_captcha_human_label(
            event_id,
            answer,
            conversation.current_image_sha256,
            actor=_telegram_actor(chat_id),
        )
    except TelegramControlError as exc:
        logger.warning("Could not save Telegram CAPTCHA label event_id=%s error=%s", event_id, exc)
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "No pude guardar la respuesta. Puede que el CAPTCHA ya haya sido "
            "revisado desde otra interfaz.",
            reply_markup=_main_menu_markup(),
        )
        return False
    _record_audit_safe(
        actor=_telegram_actor(chat_id),
        action="captcha_label",
        status="applied",
        target_type="captcha",
        target_id=event_id,
    )
    conversation.item_token = None
    conversation.current_event_id = None
    conversation.current_image_sha256 = None
    conversation.choice_answers = ()
    conversation.awaiting_manual_answer = False
    conversation.expires_at = time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS
    return True


def _send_clients(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        page = int(arguments) if arguments else 1
        if page < 1:
            raise ValueError
    except ValueError:
        telegram.send_message(chat_id, "Uso: /clientes [pagina]")
        return
    try:
        orders = admin_api.get_service_orders()
    except TelegramControlError as exc:
        logger.warning("Could not list service orders: %s", exc)
        telegram.send_message(chat_id, "No pude consultar la cola en este momento.")
        return
    total_pages = max(1, (len(orders) + CLIENTS_PAGE_SIZE - 1) // CLIENTS_PAGE_SIZE)
    if page > total_pages:
        telegram.send_message(chat_id, f"La ultima pagina disponible es {total_pages}.")
        return
    counts = _order_status_counts(orders)
    start = (page - 1) * CLIENTS_PAGE_SIZE
    visible = orders[start : start + CLIENTS_PAGE_SIZE]
    lines = [
        f"CLIENTES - PAGINA {page}/{total_pages}",
        "",
        (
            f"Activos: {counts['active']} | Pausados: {counts['paused']} | "
            f"Pendientes de pago: {counts['payment_pending']} | Cerrados: {counts['closed']}"
        ),
        "",
    ]
    for order in visible:
        applicant_name = _applicant_display_name(order)
        contact_name = _display_text(order.get("contact_name") or "Sin contacto", 32)
        lines.append(
            f"{order.get('order_id', 'sin-id')}\n"
            f"Titular: {applicant_name}\n"
            f"Contacto: {contact_name}\n"
            f"Estado: {_order_status_label(order.get('status'))} | "
            f"Prioridad: {order.get('priority', 0)}"
        )
    if not visible:
        lines.append("No hay clientes registrados.")
    if page < total_pages:
        lines.extend(["", f"Siguiente: /clientes {page + 1}"])
    keyboard: list[list[dict[str, str]]] = []
    for order in visible:
        order_id = str(order.get("order_id") or "")
        if not order_id or len(f"om:{order_id}:show_clients".encode()) > 64:
            continue
        label = _applicant_display_name(order)
        if label == "Titular no identificado por el portal":
            label = str(order.get("contact_name") or order_id)
        keyboard.append(
            [{"text": _display_text(label, 34), "callback_data": f"om:{order_id}:show_clients"}]
        )
    navigation: list[dict[str, str]] = []
    if page > 1:
        navigation.append({"text": "Anterior", "callback_data": f"ui:clients:{page - 1}"})
    if page < total_pages:
        navigation.append({"text": "Siguiente", "callback_data": f"ui:clients:{page + 1}"})
    if navigation:
        keyboard.append(navigation)
    keyboard.append(
        [
            {"text": "Actualizar", "callback_data": f"ui:clients:{page}"},
            {"text": "Menu", "callback_data": "ui:menu:main"},
        ]
    )
    telegram.send_message(
        chat_id,
        "\n\n".join(lines),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_queue(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    page = _parse_list_page(arguments, "/cola [pagina]", chat_id, telegram)
    if page is None:
        return
    try:
        orders = [
            order
            for order in admin_api.get_service_orders()
            if str(order.get("status") or "") == "ready"
        ]
    except TelegramControlError as exc:
        logger.warning("Could not list queued service orders: %s", exc)
        telegram.send_message(chat_id, "No pude consultar la cola en este momento.")
        return
    _send_operational_order_list(
        chat_id,
        page,
        orders,
        title="BUSCANDO CUPO",
        empty_text="No hay usuarios buscando cupo en este momento.",
        callback_subject="queue",
        telegram=telegram,
    )


def _send_pending_attention(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    page = _parse_list_page(arguments, "/pendientes [pagina]", chat_id, telegram)
    if page is None:
        return
    try:
        payload = admin_api.get_operator_inbox()
    except TelegramControlError as exc:
        logger.warning("Could not read operator inbox: %s", exc)
        telegram.send_message(
            chat_id,
            "La bandeja de pendientes aun no esta disponible en el Admin API. "
            "Actualiza el servicio e intenta nuevamente.",
            reply_markup={
                "inline_keyboard": [[{"text": "Menu", "callback_data": "ui:menu:main"}]]
            },
        )
        return
    raw_items = payload.get("items")
    summary = payload.get("summary")
    items = (
        [item for item in raw_items if isinstance(item, dict)]
        if isinstance(raw_items, list)
        else []
    )
    summary = summary if isinstance(summary, dict) else {}
    total_pages = max(1, (len(items) + CLIENTS_PAGE_SIZE - 1) // CLIENTS_PAGE_SIZE)
    if page > total_pages:
        telegram.send_message(chat_id, f"La ultima pagina disponible es {total_pages}.")
        return
    start = (page - 1) * CLIENTS_PAGE_SIZE
    visible = items[start : start + CLIENTS_PAGE_SIZE]
    summary_labels = (
        ("access", "Acceso"),
        ("paused", "Pausados"),
        ("contact", "Contacto"),
        ("whatsapp", "WhatsApp"),
        ("payment", "Cobros"),
        ("postpayment", "Postpago"),
        ("messages", "Mensajes"),
    )
    counts = [
        f"{label}: {int(summary.get(key) or 0)}"
        for key, label in summary_labels
        if int(summary.get(key) or 0) > 0
    ]
    lines = [
        f"PENDIENTES - PAGINA {page}/{total_pages}",
        "",
        f"Total: {int(summary.get('total') or len(items))}",
    ]
    if counts:
        lines.append(" | ".join(counts))
    keyboard: list[list[dict[str, str]]] = []
    for item in visible:
        order_id = str(item.get("order_id") or "")
        title = _display_text(item.get("title") or "Pendiente operativo", 80)
        description = _display_text(item.get("description") or "Requiere revision.", 180)
        applicant_name = _display_text(item.get("applicant_name") or order_id, 60)
        action = str(item.get("action") or "view_order")
        action_label = _display_text(item.get("action_label") or "Ver orden", 34)
        lines.extend(["", f"{title}\n{applicant_name}\n{description}"])
        if not order_id:
            continue
        if action in {"mark_payment", "register_payment"}:
            callback_data = f"py:{order_id}:choose_pending"
        elif action == "correct_credentials":
            callback_data = f"om:{order_id}:access"
        elif action == "revalidate":
            callback_data = f"om:{order_id}:validate"
        elif action in {"resolve_programs", "resolve_multiple_pending", "program_resolution"}:
            callback_data = f"pr:{order_id}:show"
        else:
            callback_data = f"om:{order_id}:show_pending"
            if action not in {"view_order"}:
                lines.append(
                    "Accion: revisar en el dashboard; Telegram no enviara ni reintentara."
                )
                action_label = "Ver orden"
        if len(callback_data.encode()) <= 64:
            button_label = _display_text(f"{action_label} - {applicant_name}", 56)
            keyboard.append([{"text": button_label, "callback_data": callback_data}])
    if not items:
        lines.extend(["", "No hay usuarios que requieran seguimiento."])
    navigation: list[dict[str, str]] = []
    if page > 1:
        navigation.append({"text": "Anterior", "callback_data": f"ui:pending:{page - 1}"})
    if page < total_pages:
        navigation.append({"text": "Siguiente", "callback_data": f"ui:pending:{page + 1}"})
    if navigation:
        keyboard.append(navigation)
    keyboard.append(
        [
            {"text": "Actualizar", "callback_data": f"ui:pending:{page}"},
            {"text": "Menu", "callback_data": "ui:menu:main"},
        ]
    )
    telegram.send_message(
        chat_id,
        "\n\n".join(lines),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_pending_payments(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    page = _parse_list_page(arguments, "/cobros [pagina]", chat_id, telegram)
    if page is None:
        return
    try:
        orders = [
            order
            for order in admin_api.get_service_orders()
            if str(order.get("status") or "") == "reserved_payment_pending"
            and str(order.get("payment_status") or "") == "pending"
        ]
    except TelegramControlError as exc:
        logger.warning("Could not list pending payments: %s", exc)
        telegram.send_message(chat_id, "No pude consultar los cobros en este momento.")
        return
    total_balance = sum((_payment_balance(order) for order in orders), Decimal("0"))
    _send_operational_order_list(
        chat_id,
        page,
        orders,
        title=f"PAGOS PENDIENTES - {len(orders)} | SALDO S/{_money_text(total_balance)}",
        empty_text="No hay reservas con pago pendiente.",
        callback_subject="payments",
        telegram=telegram,
        payment_mode=True,
    )


def _parse_list_page(
    arguments: str,
    usage: str,
    chat_id: str,
    telegram: TelegramBotApi,
) -> int | None:
    try:
        page = int(arguments) if arguments else 1
        if page < 1:
            raise ValueError
    except ValueError:
        telegram.send_message(chat_id, f"Uso: {usage}")
        return None
    return page


def _send_operational_order_list(
    chat_id: str,
    page: int,
    orders: list[dict[str, Any]],
    *,
    title: str,
    empty_text: str,
    callback_subject: str,
    telegram: TelegramBotApi,
    payment_mode: bool = False,
) -> None:
    total_pages = max(1, (len(orders) + CLIENTS_PAGE_SIZE - 1) // CLIENTS_PAGE_SIZE)
    if page > total_pages:
        telegram.send_message(chat_id, f"La ultima pagina disponible es {total_pages}.")
        return
    start = (page - 1) * CLIENTS_PAGE_SIZE
    visible = orders[start : start + CLIENTS_PAGE_SIZE]
    lines = [f"{title} - PAGINA {page}/{total_pages}", ""]
    keyboard: list[list[dict[str, str]]] = []
    for order in visible:
        order_id = str(order.get("order_id") or "")
        applicant_name = _applicant_display_name(order)
        if payment_mode:
            agreed = _money_value(order.get("amount_agreed")) or Decimal("0")
            paid = _money_value(order.get("amount_paid")) or Decimal("0")
            contact = (
                order.get("contact_whatsapp_masked")
                or order.get("contact_whatsapp_username_masked")
                or "sin contacto operativo"
            )
            appointment = " ".join(
                part
                for part in (
                    str(order.get("reservation_date") or "").strip(),
                    str(order.get("reservation_hour") or "").strip(),
                )
                if part
            ) or "sin fecha"
            communication_state = str(order.get("whatsapp_message_action_state") or "")
            communication_note = (
                "\nAtencion: revisa primero la comunicacion inicial."
                if communication_state in {"manual_required", "failed", "uncertain"}
                else ""
            )
            lines.append(
                f"{applicant_name}\n"
                f"Orden: {order_id}\n"
                f"Cita: {appointment}\n"
                f"Contacto: {contact}\n"
                f"Acordado: S/{_money_text(agreed)} | Abonado: S/{_money_text(paid)} | "
                f"Saldo: S/{_money_text(max(agreed - paid, Decimal('0')))}"
                f"{communication_note}"
            )
            callback_data = f"py:{order_id}:choose_payments"
            button_label = f"Gestionar pago - {_display_text(applicant_name, 25)}"
        else:
            lines.append(
                f"{applicant_name}\n"
                f"Orden: {order_id}\n"
                f"Estado: {_order_status_label(order.get('status'))} | "
                f"Prioridad: {order.get('priority', 0)}"
            )
            callback_data = f"om:{order_id}:show_{callback_subject}"
            button_label = _display_text(applicant_name, 34)
        if order_id and len(callback_data.encode()) <= 64:
            keyboard.append([{"text": button_label, "callback_data": callback_data}])
    if not visible:
        lines.append(empty_text)
    navigation: list[dict[str, str]] = []
    if page > 1:
        navigation.append(
            {"text": "Anterior", "callback_data": f"ui:{callback_subject}:{page - 1}"}
        )
    if page < total_pages:
        navigation.append(
            {"text": "Siguiente", "callback_data": f"ui:{callback_subject}:{page + 1}"}
        )
    if navigation:
        keyboard.append(navigation)
    keyboard.append(
        [
            {"text": "Actualizar", "callback_data": f"ui:{callback_subject}:{page}"},
            {"text": "Menu", "callback_data": "ui:menu:main"},
        ]
    )
    telegram.send_message(
        chat_id,
        "\n\n".join(lines),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_order_query(
    chat_id: str,
    command: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    order_id = arguments.strip()
    if not _valid_order_id(order_id):
        telegram.send_message(chat_id, f"Uso: /{command} ORDER_ID")
        return
    try:
        if command == "cliente":
            order = admin_api.get_service_order(order_id)
        else:
            order = next(
                (
                    item
                    for item in admin_api.get_service_orders()
                    if item.get("order_id") == order_id
                ),
                None,
            )
    except TelegramControlError as exc:
        logger.warning("Could not read service order: %s", exc)
        telegram.send_message(chat_id, "No pude consultar esa orden.")
        return
    if order is None:
        telegram.send_message(chat_id, "No pude encontrar esa orden.")
        return
    response = format_order_rules(order) if command == "reglas" else format_order_detail(order)
    reply_markup = None
    if command == "reglas":
        reply_markup = {
            "inline_keyboard": [
                [{"text": "Editar reglas", "callback_data": f"om:{order_id}:editrules"}],
                [{"text": "Volver al cliente", "callback_data": f"om:{order_id}:show"}],
            ]
        }
    telegram.send_message(chat_id, response, reply_markup=reply_markup)


def _send_priority_menu(
    chat_id: str,
    order_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        order = admin_api.get_service_order(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not prepare priority menu: %s", exc)
        telegram.send_message(chat_id, "No pude consultar la prioridad.")
        return
    current = int(order.get("priority") or 0)
    presets = [
        ("Normal", 0),
        ("Enfocada", 100),
        ("Exclusiva", 200),
    ]
    telegram.send_message(
        chat_id,
        f"PRIORIDAD\n\nOrden: {order_id}\nValor actual: {current}\n\n"
        "Normal mantiene la cola general; Enfocada prioriza la orden; "
        "Exclusiva concentra la busqueda en ella.\n\nElige un valor:",
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": label, "callback_data": f"pq:{order_id}:{value}"}
                    for label, value in presets
                ],
                [{"text": "Volver", "callback_data": f"om:{order_id}:show"}],
            ]
        },
    )


def _send_worker_panel(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        worker = admin_api.get_worker()
    except TelegramControlError as exc:
        logger.warning("Could not prepare worker panel: %s", exc)
        telegram.send_message(chat_id, "No pude consultar el worker.")
        return
    paused = bool(worker.get("paused"))
    action_row = (
        [{"text": "Reanudar", "callback_data": "wk:resume:ask"}]
        if paused
        else [{"text": "Pausar", "callback_data": "wk:pause:ask"}]
    )
    action_row.append({"text": "Reiniciar", "callback_data": "wk:restart:ask"})
    telegram.send_message(
        chat_id,
        format_worker_status(worker),
        reply_markup={
            "inline_keyboard": [
                action_row,
                [{"text": "Ver errores recientes", "callback_data": "ui:errors:show"}],
                [
                    {"text": "Actualizar", "callback_data": "ui:worker:show"},
                    {"text": "Menu", "callback_data": "ui:menu:main"},
                ],
            ]
        },
    )


def _send_opportunity_panel(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        control = admin_api.get_opportunity_control()
    except TelegramControlError as exc:
        logger.warning("Could not prepare opportunity panel: %s", exc)
        telegram.send_message(chat_id, "No pude consultar los controles de oportunidad.")
        return
    revision = control.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        telegram.send_message(chat_id, "El Admin API devolvio una revision de control invalida.")
        return

    rows: list[list[dict[str, str]]] = []
    pending_application = bool(control.get("pending_application"))
    active_burst = control.get("active_burst")
    if not pending_application:
        for target, label in (("obs006", "Rafaga"), ("obs007", "Optimizada")):
            target_control = control.get(target)
            if not isinstance(target_control, dict):
                continue
            effective = str(target_control.get("effective_mode") or "disabled")
            if target == "obs006" and isinstance(active_burst, dict):
                action = "drain"
                action_label = "Drenar"
            elif effective == "enabled":
                action = "deactivate"
                action_label = "Desactivar"
            else:
                action = "activate"
                action_label = "Activar"
            rows.append(
                [
                    {
                        "text": f"{action_label} {label}",
                        "callback_data": f"op:{target}:{action}-r{revision}",
                    }
                ]
            )

    breaker = control.get("breaker")
    if isinstance(breaker, dict) and str(breaker.get("state") or "closed") != "closed":
        rows.append([{
            "text": "Revisar y resetear breaker",
            "callback_data": f"op:obs006:reset_breaker-r{revision}",
        }])
    rows.append([
        {"text": "Actualizar", "callback_data": "ui:opportunity:show"},
        {"text": "Menu", "callback_data": "ui:menu:main"},
    ])
    telegram.send_message(
        chat_id,
        _format_opportunity_control(control),
        reply_markup={"inline_keyboard": rows},
    )


def _format_opportunity_control(control: dict[str, Any]) -> str:
    lines = [
        "CONTROL DE OPORTUNIDADES",
        "",
        f"Revision: {control.get('revision', 'desconocida')}",
    ]
    for target, label in (
        ("obs006", "Rafagas de oportunidad"),
        ("obs007", "Reobservacion de cupo perdido"),
    ):
        item = control.get(target)
        if not isinstance(item, dict):
            lines.append(f"{label}: sin datos")
            continue
        admissions = "si" if bool(item.get("admissions_allowed")) else "no"
        lines.append(
            f"{label}: deseado={item.get('desired_mode') or 'desconocido'} | "
            f"efectivo={item.get('effective_mode') or 'desconocido'} | admite={admissions}"
        )
    breaker = control.get("breaker")
    if isinstance(breaker, dict):
        lines.extend(
            [
                "",
                f"Breaker: {breaker.get('state') or 'desconocido'}",
                f"Motivo: {breaker.get('reason') or 'sin motivo activo'}",
            ]
        )
    active = control.get("active_burst")
    if isinstance(active, dict):
        lines.extend(
            [
                "",
                f"Rafaga activa: {active.get('burst_id') or 'sin id'}",
                f"Estado: {active.get('status') or 'desconocido'} | "
                f"sesiones max: {active.get('max_active_sessions') or 0} | "
                f"programados: {active.get('scheduled_clients') or 0}",
            ]
        )
    if bool(control.get("pending_application")):
        lines.extend(["", "Hay un cambio pendiente de aplicar por el worker."])
    return "\n".join(lines)


def _send_order_panel(
    chat_id: str,
    order_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    recent_orders: dict[str, deque[str]],
    *,
    return_subject: str = "clients",
) -> None:
    try:
        order = admin_api.get_service_order(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not open service order panel: %s", exc)
        telegram.send_message(chat_id, "No pude abrir ese cliente.")
        return
    history = recent_orders[chat_id]
    if order_id in history:
        history.remove(order_id)
    history.appendleft(order_id)
    keyboard = [
        [
            {"text": "Reglas", "callback_data": f"om:{order_id}:rules"},
            {"text": "Prioridad", "callback_data": f"om:{order_id}:priority"},
        ],
    ]
    if str(order.get("preflight_status") or "") == "failed":
        preflight_details = order.get("preflight_details")
        error_type = (
            str(preflight_details.get("error_type") or "")
            if isinstance(preflight_details, dict)
            else ""
        )
        if error_type == "multiple_pending_resolution_required":
            keyboard.append([{
                "text": "Resolver programas",
                "callback_data": f"pr:{order_id}:show",
            }])
        elif error_type == "invalid_credentials":
            keyboard.append([{
                "text": "Corregir acceso",
                "callback_data": f"om:{order_id}:access",
            }])
        else:
            keyboard.append([{
                "text": "Reintentar validacion",
                "callback_data": f"om:{order_id}:validate",
            }])
    if (
        str(order.get("status") or "") == "reserved_payment_pending"
        and str(order.get("payment_status") or "") == "pending"
    ):
        keyboard.append([{
            "text": "Gestionar pago",
            "callback_data": f"py:{order_id}:choose_{return_subject}",
        }])
    return_options = {
        "pending": ("Pendientes", "ui:pending:1"),
        "queue": ("Buscando cupo", "ui:queue:1"),
        "payments": ("Por cobrar", "ui:payments:1"),
        "summary": ("Citas proximas", "ui:summary:show"),
        "clients": ("Historial", "ui:clients:1"),
    }
    return_label, return_callback = return_options.get(
        return_subject,
        ("Menu", "ui:menu:main"),
    )
    keyboard.extend(
        [
            [{"text": "Actualizar", "callback_data": f"om:{order_id}:show"}],
            [
                {"text": return_label, "callback_data": return_callback},
                {"text": "Menu", "callback_data": "ui:menu:main"},
            ],
        ]
    )
    telegram.send_message(
        chat_id,
        format_order_detail(order),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_search_results(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    query = " ".join(arguments.lower().split())
    if len(query) < 2:
        telegram.send_message(
            chat_id,
            "Escribe /buscar seguido de nombre, contacto, documento visible u ORDER_ID.\n"
            "Ejemplo: /buscar Pedro",
            reply_markup={"inline_keyboard": [[{"text": "Menu", "callback_data": "ui:menu:main"}]]},
        )
        return
    try:
        matches = admin_api.search_service_orders(query)
    except TelegramControlError as exc:
        logger.warning("Could not search service orders: %s", exc)
        telegram.send_message(chat_id, "No pude buscar clientes en este momento.")
        return
    keyboard = [
        [{
            "text": _display_text(
                _applicant_display_name(order)
                if _applicant_display_name(order) != "Titular no identificado por el portal"
                else order.get("contact_name") or order.get("order_id"),
                36,
            ),
            "callback_data": f"om:{order.get('order_id')}:show_menu",
        }]
        for order in matches
        if len(f"om:{order.get('order_id')}:show_menu".encode()) <= 64
    ]
    keyboard.append([{"text": "Menu", "callback_data": "ui:menu:main"}])
    telegram.send_message(
        chat_id,
        f"BUSQUEDA: {arguments.strip()}\n\n"
        + (f"Coincidencias: {len(matches)}" if matches else "No encontre coincidencias."),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_daily_summary(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        reminders = admin_api.get_appointment_reminders()
    except TelegramControlError as exc:
        logger.warning("Could not prepare upcoming appointments: %s", exc)
        telegram.send_message(chat_id, "No pude consultar las citas proximas.")
        return
    raw_candidates = reminders.get("candidates")
    candidates = (
        [item for item in raw_candidates if isinstance(item, dict)]
        if isinstance(raw_candidates, list)
        else []
    )
    appointment_day = _format_operator_date(reminders.get("appointment_day"))
    lines = [
        "CITAS PROXIMAS / RESUMEN",
        "",
        f"Fecha: {appointment_day}",
        f"Citas: {len(candidates)}",
    ]
    keyboard: list[list[dict[str, str]]] = []
    for candidate in candidates[:8]:
        order_id = str(candidate.get("order_id") or "")
        applicant_name = _display_text(
            candidate.get("applicant_name") or order_id or "Titular no identificado",
            60,
        )
        date_label = _display_text(
            candidate.get("appointment_date_label") or appointment_day,
            40,
        )
        hour = _display_text(candidate.get("appointment_hour") or "sin hora", 24)
        site = _display_text(candidate.get("site") or "sede no registrada", 60)
        lines.extend(["", f"{applicant_name}\n{date_label} {hour}\n{site}"])
        callback_data = f"om:{order_id}:show_summary"
        if order_id and len(callback_data.encode()) <= 64:
            keyboard.append(
                [{"text": _display_text(applicant_name, 36), "callback_data": callback_data}]
            )
    if not candidates:
        lines.extend(["", "No hay citas elegibles para la fecha objetivo."])
    keyboard.append(
        [
            {"text": "Actualizar", "callback_data": "ui:summary:show"},
            {"text": "Menu", "callback_data": "ui:menu:main"},
        ]
    )
    telegram.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup={"inline_keyboard": keyboard},
    )


def _start_new_client_conversation(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    confirmation_lock: Lock,
) -> None:
    if arguments:
        telegram.send_message(chat_id, "Uso: /cliente_nuevo")
        return
    with confirmation_lock:
        _cancel_pending_client_creation_unlocked(chat_id, pending_creations)
        conversations[chat_id] = NewClientConversation(
            chat_id=chat_id,
            session_id=secrets.token_hex(4),
            values={},
            step=0,
            expires_at=time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS,
        )
    conversation = conversations[chat_id]
    message = (
        "ALTA MANUAL\n\nPaso 1: elige el tipo de documento.\n"
        "La contrasena se ocultara y el mensaje donde la escribas se intentara borrar. "
        "Puedes cancelar con /cancelar."
    )
    telegram.send_message(
        chat_id,
        message,
        reply_markup=_new_client_prompt_markup(conversation),
    )


def _process_new_client_message(
    chat_id: str,
    text: str,
    telegram: TelegramBotApi,
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        conversation = conversations.get(chat_id)
    if conversation is None:
        return False
    if conversation.expires_at <= time.monotonic():
        with confirmation_lock:
            conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "El registro vencio. Inicia nuevamente con /cliente_nuevo.",
        )
        return True
    return _continue_new_client_conversation(
        conversation,
        text.strip(),
        telegram,
        conversations,
        pending_creations,
        confirmation_lock,
    )


def _continue_new_client_conversation(
    conversation: NewClientConversation,
    value: str,
    telegram: TelegramBotApi,
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    confirmation_lock: Lock,
) -> bool:
    chat_id = conversation.chat_id
    try:
        prompt = _apply_new_client_value(conversation, value)
    except ValueError as exc:
        conversation.expires_at = time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS
        telegram.send_message(chat_id, str(exc))
        return True
    conversation.expires_at = time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS
    if prompt is not None:
        telegram.send_message(
            chat_id,
            f"{prompt}\nTienes 3 minutos para completar este paso.",
            reply_markup=_new_client_prompt_markup(conversation),
        )
        return True
    with confirmation_lock:
        conversations.pop(chat_id, None)
        _cancel_pending_client_creation_unlocked(chat_id, pending_creations)
        creation = PendingClientCreation(
            operation_id=secrets.token_hex(6),
            chat_id=chat_id,
            values=dict(conversation.values),
            expires_at=time.monotonic() + NEW_CLIENT_CONFIRMATION_TTL_SECONDS,
        )
        pending_creations[creation.operation_id] = creation
    telegram.send_message(
        chat_id,
        _format_new_client_confirmation(creation.values),
        reply_markup={
            "inline_keyboard": [[
                {
                    "text": "Crear cliente",
                    "callback_data": f"nc:{creation.operation_id}:yes",
                },
                {"text": "Cancelar", "callback_data": f"nc:{creation.operation_id}:no"},
            ]]
        },
    )
    return True


def _telegram_service_package_option(package_key: str) -> str:
    definition = service_package_definition(package_key)
    amount = money_text(definition.total_amount)
    return definition.label if amount is None else f"{definition.label} - S/{amount}"


def _new_client_prompt_markup(conversation: NewClientConversation) -> dict[str, Any]:
    step = conversation.step
    session_id = conversation.session_id
    if step == 0:
        keyboard = [[
            {"text": "DNI", "callback_data": f"nf:{session_id}:type_dni"},
            {"text": "CE", "callback_data": f"nf:{session_id}:type_ce"},
        ]]
    elif step == 4:
        keyboard = [
            [
                {"text": "TikTok", "callback_data": f"nf:{session_id}:source_tiktok"},
                {"text": "Facebook", "callback_data": f"nf:{session_id}:source_facebook"},
            ],
            [{"text": "WhatsApp", "callback_data": f"nf:{session_id}:source_whatsapp"}],
        ]
    elif step == 5:
        keyboard = [
            [
                {
                    "text": "Numero",
                    "callback_data": f"nf:{session_id}:phone_number",
                },
                {
                    "text": "Usuario",
                    "callback_data": f"nf:{session_id}:phone_username",
                },
            ],
            [
                {
                    "text": "Omitir WhatsApp",
                    "callback_data": f"nf:{session_id}:phone_omit",
                }
            ],
        ]
    elif step == 6:
        keyboard = [
            [{
                "text": _telegram_service_package_option(SERVICE_PACKAGE_STANDARD),
                "callback_data": f"nf:{session_id}:service_standard",
            }],
            [{
                "text": _telegram_service_package_option(SERVICE_PACKAGE_RESTRICTED),
                "callback_data": f"nf:{session_id}:service_weekday",
            }],
            [{
                "text": _telegram_service_package_option(SERVICE_PACKAGE_INTEGRAL),
                "callback_data": f"nf:{session_id}:service_integral",
            }],
            [{
                "text": _telegram_service_package_option(SERVICE_PACKAGE_CUSTOM),
                "callback_data": f"nf:{session_id}:service_custom",
            }],
        ]
    elif step == 8:
        keyboard = [
            [
                {"text": "Lunes", "callback_data": f"nf:{session_id}:weekday_1"},
                {"text": "Martes", "callback_data": f"nf:{session_id}:weekday_2"},
            ],
            [
                {"text": "Miercoles", "callback_data": f"nf:{session_id}:weekday_3"},
                {"text": "Jueves", "callback_data": f"nf:{session_id}:weekday_4"},
            ],
            [
                {"text": "Viernes", "callback_data": f"nf:{session_id}:weekday_5"},
                {"text": "Sabado", "callback_data": f"nf:{session_id}:weekday_6"},
            ],
            [{"text": "Domingo", "callback_data": f"nf:{session_id}:weekday_7"}],
        ]
    elif step == 9:
        keyboard = [[
            {"text": "Sin restricciones", "callback_data": f"nf:{session_id}:rules_none"},
            {"text": "Configurar", "callback_data": f"nf:{session_id}:rules_yes"},
        ]]
    elif step in {10, 11}:
        keyboard = [[{
            "text": "Sin limite",
            "callback_data": f"nf:{session_id}:value_clear",
        }]]
    elif step == 12:
        keyboard = [
            [
                {"text": "Lun-Vie", "callback_data": f"nf:{session_id}:days_mon_fri"},
                {"text": "Lun-Sab", "callback_data": f"nf:{session_id}:days_mon_sat"},
            ],
            [
                {"text": "Solo sabado", "callback_data": f"nf:{session_id}:days_sat"},
                {"text": "Todos", "callback_data": f"nf:{session_id}:value_clear"},
            ],
        ]
    elif step == 13:
        keyboard = [[{
            "text": "Sin exclusiones",
            "callback_data": f"nf:{session_id}:value_clear",
        }]]
    else:
        keyboard = []
    if step > 0:
        keyboard.append([{"text": "Atras", "callback_data": f"nf:{session_id}:back"}])
    keyboard.append([{"text": "Cancelar", "callback_data": "ui:cancel:guided"}])
    return {"inline_keyboard": keyboard}


def _rewind_new_client(conversation: NewClientConversation) -> str:
    if conversation.step == 5 and conversation.values.pop("_whatsapp_recipient_mode", None):
        return _manual_client_step_prompt(5) or "Elige el tipo de WhatsApp."
    if conversation.step in {7, 8}:
        target_step = 6
    elif conversation.step == 9:
        target_step = 7 if conversation.values.get("service_type") == "custom" else 6
    elif (
        conversation.step == 13
        and conversation.values.get("service_type") == "selected_weekday"
    ):
        target_step = 11
    else:
        target_step = max(0, conversation.step - 1)
    fields_by_step = {
        0: ("document_type",),
        1: ("document_number",),
        2: ("password",),
        3: ("contact_name",),
        4: ("contact_source",),
        5: ("contact_whatsapp", "contact_whatsapp_username", "_whatsapp_recipient_mode"),
        6: ("service_type", "service_package", "reservation_price"),
        7: ("reservation_price",),
        8: (
            "minimum_reservation_date",
            "maximum_reservation_date",
            "allowed_weekdays",
            "excluded_date_ranges",
        ),
        9: (
            "minimum_reservation_date",
            "maximum_reservation_date",
            "allowed_weekdays",
            "excluded_date_ranges",
        ),
        10: ("minimum_reservation_date",),
        11: ("maximum_reservation_date",),
        12: ("allowed_weekdays",),
        13: ("excluded_date_ranges",),
    }
    for field_name in fields_by_step.get(target_step, ()):
        conversation.values.pop(field_name, None)
    conversation.step = target_step
    conversation.expires_at = time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS
    return (
        "Paso 1: elige el tipo de documento."
        if target_step == 0
        else _manual_client_step_prompt(target_step) or "Revisa el paso anterior."
    )


def _apply_new_client_value(
    conversation: NewClientConversation, value: str
) -> str | None:
    return _apply_manual_client_value(conversation, value)


def _fixed_service_package_values(
    package_key: str,
    *,
    service_type: str | None = None,
) -> dict[str, str]:
    definition = service_package_definition(package_key)
    reservation_price = money_text(definition.total_amount)
    if reservation_price is None:
        raise ValueError(f"El paquete {package_key} exige un monto manual.")
    return {
        "service_type": service_type or definition.default_service_type,
        "service_package": definition.key,
        "reservation_price": reservation_price,
    }


def _apply_manual_client_value(
    conversation: NewClientConversation,
    value: str,
) -> str | None:
    step = conversation.step
    normalized = value.strip()
    if step == 0:
        document_types = {
            "dni": "dni",
            "ce": "foreign_resident_card",
            "foreign_resident_card": "foreign_resident_card",
        }
        document_type = document_types.get(normalized.lower())
        if document_type is None:
            raise ValueError("Elige DNI o CE.")
        conversation.values["document_type"] = document_type
    elif step == 1:
        document_number = re.sub(r"\s", "", normalized)
        if conversation.values.get("document_type") == "dni":
            if not re.fullmatch(r"\d{8}", document_number):
                raise ValueError("El DNI debe tener exactamente 8 digitos.")
        elif not re.fullmatch(r"[A-Za-z0-9]{6,20}", document_number):
            raise ValueError("El CE debe tener entre 6 y 20 letras o numeros.")
        conversation.values["document_number"] = document_number
    elif step == 2:
        if not normalized or len(value) > 200:
            raise ValueError("La contrasena debe tener entre 1 y 200 caracteres.")
        conversation.values["password"] = value
    elif step == 3:
        contact_name = " ".join(normalized.split())
        if not 2 <= len(contact_name) <= 100:
            raise ValueError("El nombre de contacto debe tener entre 2 y 100 caracteres.")
        conversation.values["contact_name"] = contact_name
    elif step == 4:
        source = normalized.lower()
        if source not in {"tiktok", "facebook", "whatsapp"}:
            raise ValueError("Elige TikTok, Facebook o WhatsApp.")
        conversation.values["contact_source"] = source
    elif step == 5:
        mode = conversation.values.get("_whatsapp_recipient_mode")
        choice = normalized.casefold().replace(" ", "_")
        if mode is None:
            if choice in {"numero", "número", "whatsapp_numero"}:
                conversation.values["_whatsapp_recipient_mode"] = "phone"
                return "Paso 6: escribe el numero de WhatsApp."
            if choice in {"usuario", "whatsapp_usuario"}:
                conversation.values["_whatsapp_recipient_mode"] = "username"
                return "Paso 6: escribe el usuario de WhatsApp, con o sin @."
            if choice not in {"omitir", "sin_whatsapp"}:
                raise ValueError("Elige Numero, Usuario u Omitir WhatsApp.")
        else:
            try:
                if mode == "phone":
                    if not normalized:
                        raise ValueError("Escribe el numero de WhatsApp.")
                    conversation.values["contact_whatsapp"] = (
                        normalize_contact_whatsapp(normalized)
                    )
                else:
                    username = unicodedata.normalize("NFKC", normalized)
                    username = "".join(
                        character
                        for character in username
                        if unicodedata.category(character) != "Cf"
                    ).strip()
                    username = f"@{username.lstrip('@')}"
                    conversation.values["contact_whatsapp_username"] = (
                        normalize_contact_whatsapp_username(username)
                    )
            except ContactValidationError as exc:
                raise ValueError(str(exc)) from exc
            finally:
                if "contact_whatsapp" in conversation.values or (
                    "contact_whatsapp_username" in conversation.values
                ):
                    conversation.values.pop("_whatsapp_recipient_mode", None)
    elif step == 6:
        choice = normalized.casefold().replace(" ", "_")
        if choice in {"servicio_estandar", "estandar", "estándar"}:
            conversation.values.update(
                _fixed_service_package_values(SERVICE_PACKAGE_STANDARD)
            )
            conversation.step = 8
        elif choice in {"servicio_dia_elegido", "dia_elegido", "día_elegido"}:
            conversation.values.update(
                _fixed_service_package_values(
                    SERVICE_PACKAGE_RESTRICTED,
                    service_type="selected_weekday",
                )
            )
            conversation.step = 7
        elif choice in {"servicio_integral", "tramite_integral", "trámite_integral"}:
            conversation.values.update(
                _fixed_service_package_values(SERVICE_PACKAGE_INTEGRAL)
            )
            conversation.step = 8
        elif choice in {"servicio_personalizado", "personalizado"}:
            custom = service_package_definition(SERVICE_PACKAGE_CUSTOM)
            conversation.values.update(
                {
                    "service_type": custom.default_service_type,
                    "service_package": custom.key,
                }
            )
        else:
            raise ValueError(
                "Elige Estandar, Dia elegido, Tramite integral o Monto personalizado."
            )
    elif step == 7:
        if conversation.values.get("service_type") != "custom":
            raise ValueError("El monto manual solo corresponde al servicio personalizado.")
        conversation.values["reservation_price"] = _money_text(
            _validated_payment_amount(normalized)
        )
        conversation.step = 8
    elif step == 8:
        if conversation.values.get("service_type") != "selected_weekday":
            raise ValueError("El dia solo corresponde al servicio Dia elegido.")
        selected_weekday = _parse_single_weekday(normalized)
        conversation.values.update(
            {
                "minimum_reservation_date": None,
                "maximum_reservation_date": None,
                "allowed_weekdays": [selected_weekday],
                "excluded_date_ranges": [],
            }
        )
    elif step == 9:
        choice = normalized.lower().replace(" ", "_")
        if choice == "sin_restricciones":
            conversation.step = 13
            return None
        if choice not in {"con_restricciones", "configurar"}:
            raise ValueError("Elige Sin restricciones o Configurar.")
        conversation.values.update(
            {
                "minimum_reservation_date": None,
                "maximum_reservation_date": None,
                "allowed_weekdays": (
                    conversation.values.get("allowed_weekdays")
                    if conversation.values.get("service_type") == "selected_weekday"
                    else None
                ),
                "excluded_date_ranges": [],
            }
        )
    else:
        field, parsed_value = _parse_rules_step(step - 10, normalized, conversation.values)
        conversation.values[field] = parsed_value
        if step == 11:
            _validate_rules_payload(conversation.values)
            if conversation.values.get("service_type") == "selected_weekday":
                conversation.step = 12
        if step == 13:
            _validate_rules_payload(conversation.values)
    conversation.step += 1
    return _manual_client_step_prompt(conversation.step)


def _manual_client_step_prompt(step: int) -> str | None:
    prompts = {
        1: "Paso 2: escribe el numero de documento.",
        2: "Paso 3: escribe la contrasena del portal.",
        3: "Paso 4: escribe el nombre de la persona de contacto.",
        4: "Paso 5: elige de donde llego el cliente.",
        5: "Paso 6: elige si registrarás un numero o un usuario de WhatsApp.",
        6: "Paso 7: elige el servicio y precio acordados.",
        7: "Paso 8: escribe el monto personalizado total en soles.",
        8: "Paso 8: elige un dia de la semana para buscar siempre ese dia.",
        9: "Paso 8: indica si deseas configurar restricciones ahora.",
        10: "Fecha minima: escribe DD-MM-YYYY o elige Sin limite.",
        11: "Fecha maxima: escribe DD-MM-YYYY o elige Sin limite.",
        12: "Dias permitidos: elige una opcion o escribe 1,2,...7.",
        13: (
            "Fechas excluidas en DD-MM-YYYY al DD-MM-YYYY; "
            "separa varios rangos con ; o elige Sin exclusiones."
        ),
    }
    return prompts.get(step)


def _format_new_client_confirmation(values: dict[str, Any]) -> str:
    return (
        _format_manual_client_details(values, title="CONFIRMAR ALTA MANUAL")
        + "\n\nRevisa todos los datos antes de crear el cliente. "
        "La confirmacion vence en 2 minutos."
    )


def _format_manual_client_details(values: dict[str, Any], *, title: str) -> str:
    weekdays = values.get("allowed_weekdays")
    weekday_text = (
        ", ".join(_weekday_name(day) for day in weekdays)
        if isinstance(weekdays, (list, tuple)) and weekdays
        else "todos"
    )
    document_type = "DNI" if values.get("document_type") == "dni" else "CE"
    return "\n".join(
        [
            title,
            "",
            f"Tipo: {document_type}",
            f"Documento: {values.get('document_number') or 'no disponible'}",
            "Contrasena: registrada (oculta por seguridad)",
            f"Contacto: {values.get('contact_name') or 'no disponible'}",
            f"Fuente: {values.get('contact_source') or 'no disponible'}",
            "WhatsApp: "
            + str(
                values.get("contact_whatsapp")
                or values.get("contact_whatsapp_username")
                or "no registrado"
            ),
            "",
            "Servicio: "
            + _service_type_label(
                values.get("service_type"), values.get("service_package")
            ),
            "Precio acordado: S/"
            + str(values.get("reservation_price") or DEFAULT_RESERVATION_PRICE_TEXT),
            "Alcance: " + _service_scope_text(values),
            "",
            "Fecha minima: "
            + _format_operator_date(values.get("minimum_reservation_date")),
            "Fecha maxima: "
            + _format_operator_date(values.get("maximum_reservation_date")),
            f"Dias permitidos: {weekday_text}",
            "Fechas excluidas: "
            + _format_excluded_date_ranges(values.get("excluded_date_ranges")),
        ]
    )


def _service_type_label(value: Any, service_package: Any = None) -> str:
    return service_package_label(
        str(service_package) if service_package else None,
        str(value) if value else None,
    )


def _service_scope_text(values: dict[str, Any]) -> str:
    if values.get("service_type") != "selected_weekday":
        return "fecha compatible segun las restricciones indicadas"
    weekdays = values.get("allowed_weekdays") or []
    selected_weekday = _weekday_name(weekdays[0]) if weekdays else "dia indicado"
    return f"solo en {selected_weekday}; no reservar otro dia de la semana"


def _send_recent_errors(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        worker = admin_api.get_worker()
        runs = admin_api.get_runs(limit=50)
    except TelegramControlError as exc:
        logger.warning("Could not read recent errors: %s", exc)
        telegram.send_message(chat_id, "No pude consultar los incidentes recientes.")
        return
    failures = [run for run in runs if _is_failed_run(run)][:5]
    lines = ["ULTIMOS ERRORES", ""]
    if worker.get("last_error"):
        lines.append("El worker conserva un error reciente. Revisa el dashboard para el detalle.")
    if not failures and not worker.get("last_error"):
        lines.append("No hay errores recientes en las ultimas 50 ejecuciones.")
    for run in failures:
        timestamp = _format_lima_datetime(run.get("finished_at") or run.get("started_at"))
        order_id = run.get("order_id") or "sin orden"
        status = run.get("status") or "error"
        message = _safe_run_message(run.get("message"))
        lines.append(
            f"{timestamp or 'Sin fecha'} | {order_id}\n"
            f"{status}: {message}"
        )
    telegram.send_message(
        chat_id,
        "\n\n".join(lines),
        reply_markup={
            "inline_keyboard": [[
                {"text": "Actualizar", "callback_data": "ui:errors:show"},
                {"text": "Menu", "callback_data": "ui:menu:main"},
            ]]
        },
    )


def format_order_detail(order: dict[str, Any]) -> str:
    applicant_name = _applicant_display_name(order)
    contact_name = _display_text(order.get("contact_name") or "Sin contacto", 60)
    lines = [
        "DETALLE DE ORDEN",
        "",
        f"Orden: {order.get('order_id') or 'desconocida'}",
        f"Cliente / titular: {applicant_name}",
        f"Tipo de documento: {order.get('document_type') or 'no disponible'}",
        f"Documento: {order.get('document_number_masked') or 'no disponible'}",
        "",
        f"Contacto: {contact_name}",
        "WhatsApp: "
        + str(
            order.get("contact_whatsapp_masked")
            or order.get("contact_whatsapp_username_masked")
            or "no registrado"
        ),
        f"Fuente: {order.get('contact_source') or 'no registrada'}",
        "",
        f"Estado: {_order_status_label(order.get('status'))}",
        f"Validacion: {_preflight_status_label(order.get('preflight_status'))}",
        f"Prioridad: {order.get('priority', 0)}",
        "Servicio: "
        + _service_type_label(order.get("service_type"), order.get("service_package")),
        "Precio acordado: S/"
        + str(order.get("reservation_price") or DEFAULT_RESERVATION_PRICE_TEXT),
        f"Reserva: {_reservation_status_label(order.get('reservation_status'))}",
        f"Pago: {_payment_status_label(order.get('payment_status'))}",
    ]
    if order.get("amount_agreed") is not None:
        agreed = _money_value(order.get("amount_agreed")) or Decimal("0")
        paid = _money_value(order.get("amount_paid")) or Decimal("0")
        lines.append(
            f"Cobro: acordado S/{_money_text(agreed)} | abonado S/{_money_text(paid)} | "
            f"saldo S/{_money_text(max(agreed - paid, Decimal('0')))}"
        )
    if order.get("reservation_date") or order.get("reservation_hour"):
        lines.append(
            "Cita: "
            f"{_format_operator_date(order.get('reservation_date'))} "
            f"{order.get('reservation_hour') or 'sin hora'}"
        )
    return "\n".join(lines)


def format_order_rules(order: dict[str, Any]) -> str:
    weekdays = order.get("allowed_weekdays")
    if isinstance(weekdays, list) and weekdays:
        weekday_text = ", ".join(_weekday_name(day) for day in weekdays)
    else:
        weekday_text = "todos"
    return "\n".join(
        [
            "REGLAS DE RESERVA",
            "",
            f"Orden: {order.get('order_id') or 'desconocida'}",
            "Fecha minima: "
            + _format_operator_date(order.get("minimum_reservation_date")),
            "Fecha maxima: "
            + _format_operator_date(order.get("maximum_reservation_date")),
            f"Dias permitidos: {weekday_text}",
            "Fechas excluidas: "
            + _format_excluded_date_ranges(order.get("excluded_date_ranges")),
        ]
    )


def _order_status_counts(orders: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"active": 0, "paused": 0, "payment_pending": 0, "closed": 0}
    for order in orders:
        status = str(order.get("status") or "")
        if status == "paused":
            counts["paused"] += 1
        elif status == "reserved_payment_pending":
            counts["payment_pending"] += 1
        elif status in {"archived", "paid", "completed", "no_charge"}:
            counts["closed"] += 1
        else:
            counts["active"] += 1
    return counts


def _order_status_label(value: Any) -> str:
    status = str(value or "")
    return {
        "ready": "Buscando cupo",
        "validation_pending": "Validando acceso",
        "paused": "Pausado",
        "reserved_payment_pending": "Reservado; pago pendiente",
        "paid": "Pagado",
        "completed": "Completado",
        "archived": "Archivado",
        "no_charge": "Cerrado sin cobro",
    }.get(status, status.replace("_", " ") or "Desconocido")


def _preflight_status_label(value: Any) -> str:
    status = str(value or "")
    return {
        "not_required": "No requerida",
        "pending": "Pendiente",
        "running": "En curso",
        "validated": "Acceso correcto",
        "failed": "Requiere revision",
    }.get(status, status.replace("_", " ") or "Desconocida")


def _reservation_status_label(value: Any) -> str:
    status = str(value or "")
    return {
        "pending": "Pendiente",
        "reserved": "Reservada",
        "confirmed": "Confirmada",
        "completed": "Completada",
        "unconfirmed": "Requiere revision",
    }.get(status, status.replace("_", " ") or "Sin reserva")


def _payment_status_label(value: Any) -> str:
    status = str(value or "")
    return {
        "pending": "Pendiente",
        "paid": "Pagado",
        "no_charge": "Sin cobro",
    }.get(status, status.replace("_", " ") or "Sin pago")


def _is_failed_run(run: dict[str, Any]) -> bool:
    try:
        exit_code = int(run.get("exit_code") or 0)
    except (TypeError, ValueError):
        exit_code = 0
    status = str(run.get("status") or "").lower()
    return exit_code != 0 or status in {
        "error",
        "failed",
        "unknown",
        "reservation_unconfirmed",
    }


def _safe_run_message(value: Any) -> str:
    text = sanitize_text(str(value or "Sin mensaje"))
    text = re.sub(r"(?i)[a-z]:[\\/][^\s]+", "[ruta]", text)
    text = re.sub(r"https?://\S+", "[url]", text)
    return _short_text(text, 160)


def _short_text(value: Any, limit: int) -> str:
    text = sanitize_text(" ".join(str(value).split()))
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _display_text(value: Any, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _applicant_display_name(order: dict[str, Any]) -> str:
    applicant_name = " ".join(str(order.get("applicant_name") or "").split())
    document_number = "".join(str(order.get("document_number") or "").split())
    masked_document = "".join(str(order.get("document_number_masked") or "").split())
    if not applicant_name:
        return "Titular no identificado por el portal"
    normalized_applicant = "".join(applicant_name.split())
    if document_number and normalized_applicant == document_number:
        return "Titular no identificado por el portal"
    if masked_document and normalized_applicant == masked_document:
        return "Titular no identificado por el portal"
    if re.fullmatch(r"\d{8,16}", normalized_applicant):
        return "Titular no identificado por el portal"
    return _display_text(applicant_name, 60)


def _valid_order_id(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) is not None


def _money_value(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        amount = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() else None


def _validated_payment_amount(value: Any) -> Decimal:
    amount = _money_value(value)
    if amount is None or amount <= 0 or amount > Decimal("99999.99"):
        raise ValueError("El monto total debe ser mayor que cero y menor que S/100000.")
    if amount.as_tuple().exponent < -2:
        raise ValueError("El monto total admite como maximo dos decimales.")
    return amount.quantize(Decimal("0.01"))


def _money_text(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _payment_balance(order: dict[str, Any]) -> Decimal:
    agreed = _money_value(order.get("amount_agreed")) or Decimal("0")
    paid = _money_value(order.get("amount_paid")) or Decimal("0")
    return max(agreed - paid, Decimal("0"))


def _weekday_name(value: Any) -> str:
    names = {
        1: "lunes",
        2: "martes",
        3: "miercoles",
        4: "jueves",
        5: "viernes",
        6: "sabado",
        7: "domingo",
    }
    try:
        return names.get(int(value), str(value))
    except (TypeError, ValueError):
        return "desconocido"


def _parse_single_weekday(value: str) -> int:
    normalized = unicodedata.normalize("NFKD", value.strip().casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    weekdays = {
        "1": 1,
        "lunes": 1,
        "2": 2,
        "martes": 2,
        "3": 3,
        "miercoles": 3,
        "4": 4,
        "jueves": 4,
        "5": 5,
        "viernes": 5,
        "6": 6,
        "sabado": 6,
        "7": 7,
        "domingo": 7,
    }
    weekday = weekdays.get(normalized)
    if weekday is None:
        raise ValueError("Elige un dia entre lunes y domingo.")
    return weekday


def _request_priority_change(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> None:
    parts = arguments.split()
    if len(parts) != 2 or not _valid_order_id(parts[0]):
        telegram.send_message(chat_id, "Uso: /prioridad ORDER_ID VALOR")
        return
    try:
        priority = int(parts[1])
        if priority < 0:
            raise ValueError
    except ValueError:
        telegram.send_message(chat_id, "La prioridad debe ser un entero no negativo.")
        return
    try:
        order = admin_api.get_service_order(parts[0])
    except TelegramControlError as exc:
        logger.warning("Could not prepare priority change: %s", exc)
        telegram.send_message(chat_id, "No pude encontrar o consultar esa orden.")
        return
    original_priority = int(order.get("priority") or 0)
    if priority == original_priority:
        telegram.send_message(chat_id, f"La prioridad ya es {priority}. No hay cambios.")
        return
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action="priority",
        order_id=parts[0],
        original={"priority": original_priority},
        updated={"priority": priority},
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)


def _request_credentials_change(
    chat_id: str,
    order_id: str,
    password: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
    *,
    return_subject: str,
) -> None:
    try:
        order = admin_api.get_service_order(order_id)
        credentials = admin_api.get_service_order_credentials(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not prepare Telegram credential correction: %s", exc)
        telegram.send_message(
            chat_id,
            "No pude preparar la correccion. La contrasena no fue modificada.",
        )
        return
    preflight_details = order.get("preflight_details")
    error_type = (
        str(preflight_details.get("error_type") or "")
        if isinstance(preflight_details, dict)
        else ""
    )
    if (
        str(order.get("preflight_status") or "") != "failed"
        or error_type != "invalid_credentials"
    ):
        telegram.send_message(
            chat_id,
            "El acceso ya no figura como credenciales rechazadas. "
            "No se guardo la contrasena.",
        )
        return
    document_number = str(credentials.get("username") or "").strip()
    document_type = str(credentials.get("document_type") or "").strip()
    current_password = str(credentials.get("password") or "")
    if not document_number or not document_type or not current_password:
        telegram.send_message(
            chat_id,
            "No pude verificar el acceso protegido actual. No se realizo ningun cambio.",
        )
        return
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action="credentials",
        order_id=order_id,
        original={
            "applicant_name": order.get("applicant_name") or "sin nombre",
            "document_number": document_number,
            "document_type": document_type,
            "password_sha256": hashlib.sha256(current_password.encode("utf-8")).hexdigest(),
            "preflight_cycle": int(order.get("preflight_cycle") or 0),
        },
        updated={
            "document_number": document_number,
            "document_type": document_type,
            "password": password,
        },
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
        return_subject=return_subject,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)


def _send_payment_menu(
    chat_id: str,
    order_id: str,
    return_subject: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        order = admin_api.get_service_order(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not prepare payment menu: %s", exc)
        telegram.send_message(chat_id, "No pude consultar ese cobro.")
        return
    if (
        str(order.get("status") or "") != "reserved_payment_pending"
        or str(order.get("payment_status") or "") != "pending"
    ):
        telegram.send_message(chat_id, "Ese cobro ya no esta pendiente. Actualiza la lista.")
        return
    agreed = _money_value(order.get("amount_agreed"))
    paid = _money_value(order.get("amount_paid")) or Decimal("0")
    if agreed is None or agreed <= 0:
        telegram.send_message(chat_id, "La orden no tiene un monto acordado valido.")
        return
    telegram.send_message(
        chat_id,
        "GESTIONAR PAGO\n\n"
        f"Cliente: {_applicant_display_name(order)}\n"
        f"Acordado: S/{_money_text(agreed)}\n"
        f"Abonado: S/{_money_text(paid)}\n"
        f"Saldo: S/{_money_text(max(agreed - paid, Decimal('0')))}\n\n"
        "El pago completo encola el postpago. Un abono conserva el cobro pendiente.",
        reply_markup={
            "inline_keyboard": [
                [{
                    "text": f"Confirmar pago completo · S/{_money_text(agreed)}",
                    "callback_data": f"py:{order_id}:full_{return_subject}",
                }],
                [{
                    "text": "Registrar abono",
                    "callback_data": f"py:{order_id}:partial_{return_subject}",
                }],
                [{"text": "Cancelar", "callback_data": "ui:cancel:guided"}],
            ]
        },
    )


def _request_payment_change(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
    *,
    return_subject: str = "menu",
) -> None:
    parts = arguments.split()
    if len(parts) not in {1, 2} or not _valid_order_id(parts[0]):
        telegram.send_message(chat_id, "Uso: /pago ORDER_ID MONTO_TOTAL")
        return
    try:
        order = admin_api.get_service_order(parts[0])
    except TelegramControlError as exc:
        logger.warning("Could not prepare payment registration: %s", exc)
        telegram.send_message(chat_id, "No pude encontrar o consultar esa orden.")
        return
    if (
        str(order.get("status") or "") != "reserved_payment_pending"
        or str(order.get("payment_status") or "") != "pending"
    ):
        telegram.send_message(
            chat_id,
            "La orden ya no figura como reserva con pago pendiente. Actualiza Cobros.",
        )
        return
    agreed = _money_value(order.get("amount_agreed"))
    if agreed is None or agreed <= 0:
        telegram.send_message(chat_id, "La orden no tiene un monto acordado valido.")
        return
    try:
        paid = _validated_payment_amount(parts[1] if len(parts) == 2 else agreed)
    except ValueError as exc:
        telegram.send_message(chat_id, str(exc))
        return
    previous_paid = _money_value(order.get("amount_paid")) or Decimal("0")
    if paid <= previous_paid:
        telegram.send_message(
            chat_id,
            f"El total acumulado debe ser mayor que S/{_money_text(previous_paid)}.",
        )
        return
    action = "payment_partial" if paid < agreed else "payment_paid"
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action=action,
        order_id=parts[0],
        original={
            "applicant_name": _applicant_display_name(order),
            "amount_agreed": _money_text(agreed),
            "amount_paid": _money_text(previous_paid),
        },
        updated={
            "amount_agreed": _money_text(agreed),
            "amount_paid": _money_text(paid),
        },
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
        return_subject=return_subject,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)


def _start_rules_conversation(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> None:
    order_id = arguments.strip()
    if not _valid_order_id(order_id):
        telegram.send_message(chat_id, "Uso: /reglas_editar ORDER_ID")
        return
    try:
        order = next(
            (item for item in admin_api.get_service_orders() if item.get("order_id") == order_id),
            None,
        )
    except TelegramControlError as exc:
        logger.warning("Could not start rules conversation: %s", exc)
        telegram.send_message(chat_id, "No pude consultar esa orden.")
        return
    if order is None:
        telegram.send_message(chat_id, "No pude encontrar esa orden.")
        return
    original = _rules_payload(order)
    conversation = RulesConversation(
        chat_id=chat_id,
        order_id=order_id,
        original=original,
        updated=dict(original),
        step=0,
        expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS,
    )
    with confirmation_lock:
        _cancel_chat_order_state_unlocked(
            chat_id,
            pending_order_changes,
            rules_conversations,
        )
        rules_conversations[chat_id] = conversation
    telegram.send_message(
        chat_id,
        f"EDITAR REGLAS\n\n{format_order_rules(order)}\n\n{_rules_step_prompt(0)}",
        reply_markup=_rules_prompt_markup(0),
    )


def _process_rules_conversation_message(
    chat_id: str,
    text: str,
    telegram: TelegramBotApi,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        conversation = rules_conversations.get(chat_id)
    if conversation is None:
        return False
    if conversation.expires_at <= time.monotonic():
        with confirmation_lock:
            rules_conversations.pop(chat_id, None)
        telegram.send_message(chat_id, "La edicion de reglas vencio. Inicia nuevamente.")
        return True
    return _continue_rules_conversation(
        conversation,
        text,
        telegram,
        rules_conversations,
        pending_order_changes,
        confirmation_lock,
    )


def _continue_rules_conversation(
    conversation: RulesConversation,
    text: str,
    telegram: TelegramBotApi,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> bool:
    chat_id = conversation.chat_id
    try:
        field, value = _parse_rules_step(conversation.step, text, conversation.updated)
    except ValueError as exc:
        telegram.send_message(
            chat_id,
            f"{exc}\n\n{_rules_step_prompt(conversation.step)}",
            reply_markup=_rules_prompt_markup(conversation.step),
        )
        return True
    conversation.updated[field] = value
    conversation.step += 1
    conversation.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
    if conversation.step < 4:
        telegram.send_message(
            chat_id,
            _rules_step_prompt(conversation.step),
            reply_markup=_rules_prompt_markup(conversation.step),
        )
        return True
    try:
        _validate_rules_payload(conversation.updated)
    except ValueError as exc:
        with confirmation_lock:
            rules_conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            f"No se guardo ningun cambio: {exc}\nInicia nuevamente con /reglas_editar.",
        )
        return True
    with confirmation_lock:
        rules_conversations.pop(chat_id, None)
    if conversation.updated == conversation.original:
        telegram.send_message(chat_id, "No hay cambios en las reglas.")
        return True
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action="rules",
        order_id=conversation.order_id,
        original=conversation.original,
        updated=conversation.updated,
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)
    return True


def _parse_rules_step(
    step: int,
    text: str,
    current: dict[str, Any],
) -> tuple[str, Any]:
    value = text.strip().lower()
    fields = (
        "minimum_reservation_date",
        "maximum_reservation_date",
        "allowed_weekdays",
        "excluded_date_ranges",
    )
    field = fields[step]
    if value in {"igual", "mantener"}:
        return field, current.get(field)
    if value in {"quitar", "ninguno", "todos"}:
        return field, [] if field == "excluded_date_ranges" else None
    if step in {0, 1}:
        try:
            parsed = datetime.strptime(value, "%d-%m-%Y").date()
        except ValueError as exc:
            raise ValueError("Usa DD-MM-YYYY, igual o quitar.") from exc
        return field, parsed.isoformat()
    if step == 3:
        ranges = []
        for item in value.split(";"):
            item = item.strip()
            match = re.fullmatch(
                r"(\d{2}-\d{2}-\d{4})(?:\s+(?:a|al|hasta)\s+"
                r"(\d{2}-\d{2}-\d{4}))?",
                item,
            )
            if match is None:
                raise ValueError(
                    "Usa DD-MM-YYYY o DD-MM-YYYY al DD-MM-YYYY; separa varios con ;"
                )
            try:
                start = datetime.strptime(match.group(1), "%d-%m-%Y").date()
                end = datetime.strptime(
                    match.group(2) or match.group(1),
                    "%d-%m-%Y",
                ).date()
            except ValueError as exc:
                raise ValueError("Una de las fechas excluidas no es valida.") from exc
            if end < start:
                raise ValueError("Una fecha excluida no puede terminar antes de comenzar.")
            ranges.append({"start_date": start.isoformat(), "end_date": end.isoformat()})
        return field, ranges
    try:
        weekdays = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    except ValueError as exc:
        raise ValueError("Usa dias ISO separados por coma, igual o todos.") from exc
    if not weekdays or any(day < 1 or day > 7 for day in weekdays):
        raise ValueError("Los dias deben estar entre 1=lunes y 7=domingo.")
    return field, weekdays


def _rules_step_prompt(step: int) -> str:
    return (
        "Paso 1/4 - Fecha minima. Responde DD-MM-YYYY, mantener o sin limite.",
        "Paso 2/4 - Fecha maxima. Responde DD-MM-YYYY, mantener o sin limite.",
        "Paso 3/4 - Dias permitidos. Usa los botones o responde 1,2,...7.",
        "Paso 4/4 - Fechas excluidas. Usa DD-MM-YYYY al DD-MM-YYYY; "
        "separa varios rangos con ; o elige Sin exclusiones.",
    )[step]


def _rules_prompt_markup(step: int) -> dict[str, Any]:
    if step in {0, 1}:
        rows = [[
            {"text": "Mantener", "callback_data": "rf:value:keep"},
            {"text": "Quitar limite", "callback_data": "rf:value:clear"},
        ]]
    elif step == 2:
        rows = [
            [
                {"text": "Lun-Vie", "callback_data": "rf:days:mon_fri"},
                {"text": "Lun-Sab", "callback_data": "rf:days:mon_sat"},
            ],
            [{"text": "Solo sabado", "callback_data": "rf:days:sat"}],
            [
                {"text": "Todos", "callback_data": "rf:value:clear"},
                {"text": "Mantener", "callback_data": "rf:value:keep"},
            ],
        ]
    else:
        rows = [[
            {"text": "Sin exclusiones", "callback_data": "rf:value:clear"},
            {"text": "Mantener", "callback_data": "rf:value:keep"},
        ]]
    if step > 0:
        rows.append([{"text": "Atras", "callback_data": "rf:nav:back"}])
    rows.append([{"text": "Cancelar", "callback_data": "ui:cancel:guided"}])
    return {"inline_keyboard": rows}


def _validate_rules_payload(rules: dict[str, Any]) -> None:
    minimum = rules.get("minimum_reservation_date")
    maximum = rules.get("maximum_reservation_date")
    if minimum and maximum and date.fromisoformat(maximum) < date.fromisoformat(minimum):
        raise ValueError("la fecha maxima no puede ser anterior a la minima")


def _rules_payload(order: dict[str, Any]) -> dict[str, Any]:
    weekdays = order.get("allowed_weekdays")
    return {
        "minimum_reservation_date": order.get("minimum_reservation_date"),
        "maximum_reservation_date": order.get("maximum_reservation_date"),
        "allowed_weekdays": list(weekdays) if isinstance(weekdays, list) else None,
        "excluded_date_ranges": list(order.get("excluded_date_ranges") or []),
    }


def _store_order_change(
    change: PendingOrderChange,
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> None:
    with confirmation_lock:
        stale = [
            key
            for key, item in pending_order_changes.items()
            if item.chat_id == change.chat_id
        ]
        for key in stale:
            pending_order_changes.pop(key, None)
        pending_order_changes[change.operation_id] = change


def _send_order_change_confirmation(
    change: PendingOrderChange,
    telegram: TelegramBotApi,
) -> None:
    comparison = _format_order_change_comparison(change)
    telegram.send_message(
        change.chat_id,
        f"CONFIRMAR CAMBIO\n\n{comparison}\n\nLa confirmacion vence en 2 minutos.",
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": "Confirmar", "callback_data": f"oc:{change.operation_id}:yes"},
                    {"text": "Cancelar", "callback_data": f"oc:{change.operation_id}:no"},
                ]
            ]
        },
    )


def _format_order_change_comparison(change: PendingOrderChange) -> str:
    if change.action == "priority":
        return (
            f"Orden: {change.order_id}\n"
            f"Prioridad anterior: {change.original['priority']}\n"
            f"Prioridad nueva: {change.updated['priority']}"
        )
    if change.action == "credentials":
        return (
            f"Cliente / titular: {change.original['applicant_name']}\n"
            f"Orden: {change.order_id}\n"
            "Cambio: reemplazar la contrasena del portal.\n\n"
            "La contrasena no se mostrara. La cuenta y sus subordenes quedaran "
            "pausadas hasta terminar una validacion automatica con el nuevo acceso."
        )
    if change.action in {"payment_paid", "payment_partial"}:
        consequence = (
            "Al confirmar, se guardara el abono y el cobro seguira pendiente. "
            "No se encolara el postpago."
            if change.action == "payment_partial"
            else "Al confirmar, el pago pasara a paid y se encolara automaticamente "
            "el seguimiento postpago por WhatsApp."
        )
        return (
            f"Cliente / titular: {change.original['applicant_name']}\n"
            f"Orden: {change.order_id}\n"
            f"Monto acordado: S/{change.updated['amount_agreed']}\n"
            f"Registrado anteriormente: S/{change.original['amount_paid']}\n"
            f"Total que quedara pagado: S/{change.updated['amount_paid']}\n\n"
            f"{consequence}"
        )
    return "\n".join(
        [
            f"Orden: {change.order_id}",
            "",
            "Fecha minima: "
            + _change_value(change.original, change.updated, "minimum_reservation_date"),
            "Fecha maxima: "
            + _change_value(change.original, change.updated, "maximum_reservation_date"),
            f"Dias: {_change_value(change.original, change.updated, 'allowed_weekdays')}",
            "Fechas excluidas: "
            + _change_value(change.original, change.updated, "excluded_date_ranges"),
        ]
    )


def _change_value(original: dict[str, Any], updated: dict[str, Any], field: str) -> str:
    old = original.get(field)
    new = updated.get(field)
    if field in {"minimum_reservation_date", "maximum_reservation_date"}:
        return f"{_format_operator_date(old)} -> {_format_operator_date(new)}"
    if field == "excluded_date_ranges":
        return f"{_format_excluded_date_ranges(old)} -> {_format_excluded_date_ranges(new)}"
    if field == "allowed_weekdays":
        old_days = ", ".join(_weekday_name(day) for day in (old or [])) or "todos"
        new_days = ", ".join(_weekday_name(day) for day in (new or [])) or "todos"
        return f"{old_days} -> {new_days}"
    old_text = old if old is not None else "sin limite"
    new_text = new if new is not None else "sin limite"
    return f"{old_text} -> {new_text}"


def _format_operator_date(value: Any) -> str:
    if value in {None, ""}:
        return "sin limite"
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return "fecha invalida"
    return parsed.strftime("%d-%m-%Y")


def _format_excluded_date_ranges(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "ninguna"
    labels = []
    for item in value:
        if not isinstance(item, dict):
            continue
        start = _format_operator_date(item.get("start_date"))
        end = _format_operator_date(item.get("end_date"))
        labels.append(start if start == end else f"{start} al {end}")
    return "; ".join(labels) if labels else "ninguna"


def _request_worker_confirmation(
    chat_id: str,
    command: str,
    telegram: TelegramBotApi,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    confirmation_lock: Lock,
) -> None:
    operation_id = secrets.token_hex(6)
    confirmation = PendingWorkerConfirmation(
        operation_id=operation_id,
        chat_id=chat_id,
        command=command,
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
    )
    with confirmation_lock:
        _cancel_chat_confirmations_unlocked(chat_id, pending_confirmations)
        pending_confirmations[operation_id] = confirmation
    label = _worker_command_label(command)
    telegram.send_message(
        chat_id,
        f"Confirmar: {label}.\n\nLa confirmacion vence en 2 minutos.",
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "Confirmar",
                        "callback_data": f"wc:{operation_id}:yes",
                    },
                    {
                        "text": "Cancelar",
                        "callback_data": f"wc:{operation_id}:no",
                    },
                ]
            ]
        },
    )


def _request_opportunity_confirmation(
    chat_id: str,
    action: str,
    target: str,
    expected_revision: int,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    confirmation_lock: Lock,
) -> None:
    try:
        current = admin_api.get_opportunity_control()
    except TelegramControlError as exc:
        logger.warning("Could not review opportunity control before confirmation: %s", exc)
        telegram.send_message(chat_id, "No pude revisar el estado actual. Actualiza el panel.")
        return
    if current.get("revision") != expected_revision:
        telegram.send_message(
            chat_id,
            "El control cambio desde que abriste el panel. Revisa el estado actualizado.",
        )
        _send_opportunity_panel(chat_id, telegram, admin_api)
        return

    reason = {
        "activate": "Activacion confirmada por el operador desde Telegram.",
        "deactivate": "Desactivacion confirmada por el operador desde Telegram.",
        "drain": "Drenaje controlado confirmado por el operador desde Telegram.",
        "reset_breaker": "Reset manual del breaker confirmado tras revision en Telegram.",
    }[action]
    operation_id = secrets.token_hex(6)
    confirmation = PendingWorkerConfirmation(
        operation_id=operation_id,
        chat_id=chat_id,
        command=f"opportunity:{action}",
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
        opportunity_target=target,
        expected_revision=expected_revision,
        reason=reason,
    )
    with confirmation_lock:
        _cancel_chat_confirmations_unlocked(chat_id, pending_confirmations)
        pending_confirmations[operation_id] = confirmation
    label = {
        "activate": "activar",
        "deactivate": "desactivar",
        "drain": "drenar sin abrir nuevas sesiones",
        "reset_breaker": "resetear el breaker revisado",
    }[action]
    consequence = (
        " Al resetear, volvera a regir el modo deseado actual y las admisiones "
        "podran reanudarse."
        if action == "reset_breaker"
        else ""
    )
    telegram.send_message(
        chat_id,
        f"Confirmar: {label} {target}.\n\n"
        f"Revision revisada: {expected_revision}.{consequence} "
        "La confirmacion vence en 2 minutos.",
        reply_markup={
            "inline_keyboard": [[
                {"text": "Confirmar", "callback_data": f"wc:{operation_id}:yes"},
                {"text": "Cancelar", "callback_data": f"wc:{operation_id}:no"},
            ]]
        },
    )


def _process_interface_callback(
    callback_id: str,
    data: str,
    message: Any,
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    pending_order_changes: dict[str, PendingOrderChange],
    pending_client_creations: dict[str, PendingClientCreation],
    new_client_conversations: dict[str, NewClientConversation],
    rules_conversations: dict[str, RulesConversation],
    search_conversations: dict[str, SearchConversation],
    captcha_conversations: dict[str, CaptchaReviewConversation],
    recent_orders: dict[str, deque[str]],
    confirmation_lock: Lock,
) -> bool:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in {
        "ui", "om", "op", "pq", "py", "wk", "nf", "rf", "pr"
    }:
        return False
    prefix, subject, action = parts
    telegram.answer_callback_query(callback_id, "Procesando...")
    if prefix == "pr":
        if action in {"informed", "keep"}:
            telegram_program_resolution.set_communication_decision(
                chat_id, subject, action, telegram,
                pending_order_changes, confirmation_lock,
            )
        elif not _valid_order_id(subject):
            telegram.send_message(chat_id, "La orden seleccionada no es valida.")
        elif action == "show":
            telegram_program_resolution.send_panel(chat_id, subject, telegram, admin_api)
        else:
            telegram_program_resolution.request_resolution(
                chat_id, subject, action, telegram, admin_api,
                pending_order_changes, confirmation_lock, PendingOrderChange,
                confirmation_ttl_seconds=CONFIRMATION_TTL_SECONDS,
            )
        return True
    if prefix == "ui":
        if subject == "menu":
            _send_main_menu(chat_id, telegram, admin_api)
        elif subject == "status":
            _send_worker_panel(chat_id, telegram, admin_api)
        elif subject == "clients":
            _send_clients(chat_id, action, telegram, admin_api)
        elif subject == "pending":
            _send_pending_attention(chat_id, action, telegram, admin_api)
        elif subject == "queue":
            _send_queue(chat_id, action, telegram, admin_api)
        elif subject == "payments":
            _send_pending_payments(chat_id, action, telegram, admin_api)
        elif subject == "manual":
            search_conversations.pop(chat_id, None)
            captcha_conversations.pop(chat_id, None)
            _cancel_chat_order_state(
                chat_id,
                pending_order_changes,
                rules_conversations,
                confirmation_lock,
            )
            _start_new_client_conversation(
                chat_id,
                "",
                telegram,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
        elif subject == "search":
            captcha_conversations.pop(chat_id, None)
            _cancel_chat_client_state(
                chat_id,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
            _cancel_chat_order_state(
                chat_id,
                pending_order_changes,
                rules_conversations,
                confirmation_lock,
            )
            search_conversations[chat_id] = SearchConversation(
                expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS
            )
            telegram.send_message(
                chat_id,
                "BUSCAR CLIENTE\n\nEscribe el nombre, documento, WhatsApp u orden. "
                "Puedes cancelar con /cancelar.",
            )
        elif subject == "captcha":
            _cancel_chat_client_state(
                chat_id,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
            _cancel_chat_order_state(
                chat_id,
                pending_order_changes,
                rules_conversations,
                confirmation_lock,
            )
            search_conversations.pop(chat_id, None)
            _start_captcha_review(chat_id, telegram, admin_api, captcha_conversations)
        elif subject == "summary":
            _send_daily_summary(chat_id, telegram, admin_api)
        elif subject == "worker":
            _send_worker_panel(chat_id, telegram, admin_api)
        elif subject == "tools":
            _send_tools_menu(chat_id, telegram, admin_api)
        elif subject == "opportunity":
            _send_opportunity_panel(chat_id, telegram, admin_api)
        elif subject == "errors":
            _send_recent_errors(chat_id, telegram, admin_api)
        elif subject == "delete":
            message_id = message.get("message_id") if isinstance(message, dict) else None
            if isinstance(message_id, int):
                try:
                    telegram.delete_message(chat_id, message_id)
                except TelegramControlError:
                    telegram.send_message(chat_id, "No pude eliminar ese mensaje.")
        elif subject == "cancel":
            with confirmation_lock:
                removed = new_client_conversations.pop(chat_id, None) is not None
                removed = _cancel_pending_client_creation_unlocked(
                    chat_id, pending_client_creations
                ) or removed
                removed = rules_conversations.pop(chat_id, None) is not None or removed
                removed = search_conversations.pop(chat_id, None) is not None or removed
                removed = captcha_conversations.pop(chat_id, None) is not None or removed
            telegram.send_message(
                chat_id,
                "Operacion cancelada." if removed else "No habia una operacion activa.",
                reply_markup=_main_menu_markup(),
            )
        else:
            telegram.send_message(chat_id, "Accion de menu no reconocida.")
        return True
    if prefix == "op":
        action_text, separator, revision_text = action.rpartition("-r")
        if (
            subject not in {"obs006", "obs007"}
            or action_text not in {"activate", "deactivate", "drain", "reset_breaker"}
            or not separator
            or not revision_text.isdigit()
        ):
            telegram.send_message(chat_id, "Ese control de oportunidad ya no es valido.")
            return True
        _request_opportunity_confirmation(
            chat_id,
            action_text,
            subject,
            int(revision_text),
            telegram,
            admin_api,
            pending_confirmations,
            confirmation_lock,
        )
        return True
    if prefix == "om":
        order_id = subject
        if not _valid_order_id(order_id):
            telegram.send_message(chat_id, "La orden seleccionada no es valida.")
        elif action == "show" or action.startswith("show_"):
            return_subject = action.removeprefix("show_") if action != "show" else "clients"
            _send_order_panel(
                chat_id,
                order_id,
                telegram,
                admin_api,
                recent_orders,
                return_subject=return_subject,
            )
        elif action == "rules":
            _send_order_query(chat_id, "reglas", order_id, telegram, admin_api)
        elif action == "priority":
            _send_priority_menu(chat_id, order_id, telegram, admin_api)
        elif action == "access":
            try:
                current = admin_api.get_service_order(order_id)
            except TelegramControlError as exc:
                logger.warning("Could not prepare Telegram credential correction: %s", exc)
                telegram.send_message(chat_id, "No pude revisar el acceso de ese cliente.")
                return True
            preflight_details = current.get("preflight_details")
            error_type = (
                str(preflight_details.get("error_type") or "")
                if isinstance(preflight_details, dict)
                else ""
            )
            if (
                str(current.get("preflight_status") or "") != "failed"
                or error_type != "invalid_credentials"
            ):
                telegram.send_message(
                    chat_id,
                    "El acceso ya no figura como credenciales rechazadas. "
                    "Actualiza el cliente antes de continuar.",
                )
                return True
            _cancel_chat_client_state(
                chat_id,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
            _cancel_chat_order_state(
                chat_id,
                pending_order_changes,
                rules_conversations,
                confirmation_lock,
            )
            captcha_conversations.pop(chat_id, None)
            search_conversations[chat_id] = SearchConversation(
                expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS,
                mode="credentials",
                order_id=order_id,
                return_subject="pending",
            )
            telegram.send_message(
                chat_id,
                "CORREGIR ACCESO\n\n"
                f"Cliente: {current.get('applicant_name') or 'sin nombre'}\n"
                f"Orden: {order_id}\n"
                f"Motivo: {current.get('preflight_message') or 'credenciales rechazadas'}\n\n"
                "Escribe la nueva contrasena del portal. El mensaje se intentara borrar "
                "inmediatamente y nada cambiara hasta que confirmes.\n\n"
                "Puedes cancelar con /cancelar.",
            )
        elif action == "validate":
            try:
                current = admin_api.get_service_order(order_id)
            except TelegramControlError as exc:
                logger.warning("Could not review order before revalidation: %s", exc)
                telegram.send_message(chat_id, "No pude revisar el estado actual.")
                return True
            if str(current.get("preflight_status") or "") != "failed":
                telegram.send_message(
                    chat_id,
                    "La validacion ya no esta fallida. Actualiza el cliente antes de continuar.",
                )
                return True
            operation_id = secrets.token_hex(6)
            with confirmation_lock:
                _cancel_chat_confirmations_unlocked(chat_id, pending_confirmations)
                pending_confirmations[operation_id] = PendingWorkerConfirmation(
                    operation_id=operation_id,
                    chat_id=chat_id,
                    command=f"revalidate:{order_id}",
                    expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
                    opportunity_target=order_id,
                )
            telegram.send_message(
                chat_id,
                "CONFIRMAR NUEVA VALIDACION\n\n"
                f"Orden: {order_id}\n"
                f"Motivo actual: {current.get('preflight_message') or 'sin detalle'}\n\n"
                "Se iniciara una nueva comprobacion de acceso.",
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "Volver a validar", "callback_data": f"wc:{operation_id}:yes"},
                        {"text": "Cancelar", "callback_data": f"wc:{operation_id}:no"},
                    ]]
                },
            )
        elif action == "editrules":
            search_conversations.pop(chat_id, None)
            captcha_conversations.pop(chat_id, None)
            _cancel_chat_client_state(
                chat_id,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
            _start_rules_conversation(
                chat_id,
                order_id,
                telegram,
                admin_api,
                rules_conversations,
                pending_order_changes,
                confirmation_lock,
            )
        else:
            telegram.send_message(chat_id, "Accion de cliente no reconocida.")
        return True
    if prefix == "pq":
        _request_priority_change(
            chat_id,
            f"{subject} {action}",
            telegram,
            admin_api,
            pending_order_changes,
            confirmation_lock,
        )
        return True
    if prefix == "py":
        action_name, separator, return_subject = action.partition("_")
        if action == "default":
            action_name, return_subject = "full", "menu"
        if (
            not separator
            and action != "default"
            or action_name not in {"choose", "full", "partial"}
            or return_subject
            not in {"menu", "pending", "payments", "queue", "summary", "clients"}
        ):
            telegram.send_message(chat_id, "Opcion de pago no reconocida.")
        elif action_name == "choose":
            _send_payment_menu(
                chat_id,
                subject,
                return_subject,
                telegram,
                admin_api,
            )
        elif action_name == "partial":
            search_conversations[chat_id] = SearchConversation(
                expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS,
                mode="payment",
                order_id=subject,
                return_subject=return_subject,
            )
            telegram.send_message(
                chat_id,
                "REGISTRAR ABONO\n\nEscribe el total acumulado pagado, no solo "
                "el ultimo abono. Ejemplo: 40.00\n\nPuedes cancelar con /cancelar.",
            )
        else:
            _request_payment_change(
                chat_id,
                subject,
                telegram,
                admin_api,
                pending_order_changes,
                confirmation_lock,
                return_subject=return_subject,
            )
        return True
    if prefix == "wk":
        if subject not in {"pause", "resume", "restart"}:
            telegram.send_message(chat_id, "Accion de worker no reconocida.")
        else:
            _request_worker_confirmation(
                chat_id,
                subject,
                telegram,
                pending_confirmations,
                confirmation_lock,
            )
        return True
    if prefix == "rf":
        conversation = rules_conversations.get(chat_id)
        if conversation is None:
            telegram.send_message(chat_id, "La edicion de reglas ya no esta activa.")
            return True
        if subject == "nav" and action == "back":
            if conversation.step > 0:
                conversation.step -= 1
                field = (
                    "minimum_reservation_date",
                    "maximum_reservation_date",
                    "allowed_weekdays",
                    "excluded_date_ranges",
                )[conversation.step]
                conversation.updated[field] = conversation.original.get(field)
            conversation.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
            _clear_captcha_review_buttons(chat_id, message, telegram)
            telegram.send_message(
                chat_id,
                _rules_step_prompt(conversation.step),
                reply_markup=_rules_prompt_markup(conversation.step),
            )
            return True
        values = {
            ("value", "keep"): "igual",
            ("value", "clear"): "quitar",
            ("days", "mon_fri"): "1,2,3,4,5",
            ("days", "mon_sat"): "1,2,3,4,5,6",
            ("days", "sat"): "6",
        }
        value = values.get((subject, action))
        if value is None:
            telegram.send_message(chat_id, "Opcion de reglas no reconocida.")
            return True
        _clear_captcha_review_buttons(chat_id, message, telegram)
        _continue_rules_conversation(
            conversation,
            value,
            telegram,
            rules_conversations,
            pending_order_changes,
            confirmation_lock,
        )
        return True
    conversation = new_client_conversations.get(chat_id)
    if conversation is None or conversation.expires_at <= time.monotonic():
        _cancel_chat_client_state(
            chat_id,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        telegram.send_message(
            chat_id,
            "Ese boton ya vencio. Inicia otra vez desde el menu.",
            reply_markup=_main_menu_markup(),
        )
        return True
    if conversation.session_id != subject:
        telegram.send_message(
            chat_id,
            "Ese boton pertenece a otro registro y ya no es valido.",
        )
        return True
    if action == "back":
        prompt = _rewind_new_client(conversation)
        _clear_captcha_review_buttons(chat_id, message, telegram)
        telegram.send_message(
            chat_id,
            f"{prompt}\nTienes 3 minutos para completar este paso.",
            reply_markup=_new_client_prompt_markup(conversation),
        )
        return True
    values = {
        "type_dni": "dni",
        "type_ce": "ce",
        "source_tiktok": "tiktok",
        "source_facebook": "facebook",
        "source_whatsapp": "whatsapp",
        "phone_number": "WHATSAPP_NUMERO",
        "phone_username": "WHATSAPP_USUARIO",
        "phone_omit": "OMITIR",
        "service_standard": "SERVICIO_ESTANDAR",
        "service_weekday": "SERVICIO_DIA_ELEGIDO",
        "service_integral": "SERVICIO_INTEGRAL",
        "service_custom": "SERVICIO_PERSONALIZADO",
        "rules_none": "SIN_RESTRICCIONES",
        "rules_yes": "CON_RESTRICCIONES",
        "value_clear": "quitar",
        "days_mon_fri": "1,2,3,4,5",
        "days_mon_sat": "1,2,3,4,5,6",
        "days_sat": "6",
        "weekday_1": "1",
        "weekday_2": "2",
        "weekday_3": "3",
        "weekday_4": "4",
        "weekday_5": "5",
        "weekday_6": "6",
        "weekday_7": "7",
    }
    value = values.get(action)
    if value is None:
        telegram.send_message(chat_id, "Opcion de registro no reconocida.")
        return True
    _clear_captcha_review_buttons(chat_id, message, telegram)
    _continue_new_client_conversation(
        conversation,
        value,
        telegram,
        new_client_conversations,
        pending_client_creations,
        confirmation_lock,
    )
    return True


def _process_callback_query(
    callback_query: dict[str, Any],
    config: TelegramControlConfig,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    pending_order_changes: dict[str, PendingOrderChange],
    pending_client_creations: dict[str, PendingClientCreation],
    new_client_conversations: dict[str, NewClientConversation],
    rules_conversations: dict[str, RulesConversation],
    search_conversations: dict[str, SearchConversation],
    captcha_conversations: dict[str, CaptchaReviewConversation],
    recent_orders: dict[str, deque[str]],
    rate_limiter: TelegramRateLimiter,
    confirmation_lock: Lock,
    executor: ThreadPoolExecutor,
) -> None:
    callback_id = callback_query.get("id")
    data = callback_query.get("data")
    message = callback_query.get("message")
    chat = message.get("chat") if isinstance(message, dict) else None
    if not isinstance(callback_id, str) or not isinstance(data, str):
        return
    if not isinstance(chat, dict) or chat.get("id") is None:
        return
    chat_id = str(chat["id"])
    sender = callback_query.get("from")
    user_id = str(sender.get("id") or "") if isinstance(sender, dict) else ""
    if chat_id not in config.authorized_chat_ids:
        logger.warning("Ignored Telegram callback from an unauthorized chat.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="callback", status="denied"
        )
        return
    mutation = _callback_is_mutation(data)
    if mutation and not _mutation_user_authorized(config, chat, sender):
        _record_audit_safe(
            actor=_telegram_actor(chat_id, user_id),
            action="callback",
            status="denied",
            detail="Mutation requires an authorized user in a private chat.",
        )
        telegram.answer_callback_query(
            callback_id,
            "Accion permitida solo al operador autorizado en chat privado.",
        )
        return
    if not rate_limiter.allow(chat_id, mutation=mutation):
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="callback", status="rate_limited"
        )
        telegram.answer_callback_query(callback_id, "Espera un minuto y vuelve a intentar.")
        return
    if _process_captcha_review_callback(
        callback_id,
        data,
        message,
        chat_id,
        telegram,
        admin_api,
        captcha_conversations,
    ):
        return
    if _process_interface_callback(
        callback_id,
        data,
        message,
        chat_id,
        telegram,
        admin_api,
        pending_confirmations,
        pending_order_changes,
        pending_client_creations,
        new_client_conversations,
        rules_conversations,
        search_conversations,
        captcha_conversations,
        recent_orders,
        confirmation_lock,
    ):
        return
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in {"wc", "oc", "nc"} or parts[2] not in {"yes", "no"}:
        telegram.answer_callback_query(callback_id, "Accion no reconocida.")
        return
    operation_id = parts[1]
    if parts[0] == "nc":
        with confirmation_lock:
            creation = pending_client_creations.pop(operation_id, None)
        if (
            creation is None
            or creation.chat_id != chat_id
            or creation.expires_at <= time.monotonic()
        ):
            telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
            return
        _clear_captcha_review_buttons(chat_id, message, telegram)
        if parts[2] == "no":
            _record_audit_safe(
                actor=_telegram_actor(chat_id), action="client_create",
                status="cancelled", operation_id=operation_id,
            )
            telegram.answer_callback_query(callback_id, "Operacion cancelada.")
            telegram.send_message(chat_id, "Registro cancelado. No se guardo nada.")
            return
        telegram.answer_callback_query(callback_id, "Registro confirmado.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="client_create",
            status="accepted", operation_id=operation_id,
        )
        executor.submit(_execute_client_creation, creation, telegram, admin_api)
        return
    if parts[0] == "oc":
        with confirmation_lock:
            change = pending_order_changes.pop(operation_id, None)
        if (
            change is None
            or change.chat_id != chat_id
            or change.expires_at <= time.monotonic()
        ):
            telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
            return
        _clear_captcha_review_buttons(chat_id, message, telegram)
        if parts[2] == "no":
            _record_audit_safe(
                actor=_telegram_actor(chat_id), action=change.action,
                status="cancelled", target_type="service_order",
                target_id=change.order_id, operation_id=operation_id,
            )
            telegram.answer_callback_query(callback_id, "Operacion cancelada.")
            telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
            return
        telegram.answer_callback_query(callback_id, "Cambio confirmado.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action=change.action,
            status="accepted", target_type="service_order",
            target_id=change.order_id, operation_id=operation_id,
        )
        executor.submit(_execute_order_change, change, telegram, admin_api)
        return
    with confirmation_lock:
        confirmation = pending_confirmations.pop(operation_id, None)
    if (
        confirmation is None
        or confirmation.chat_id != chat_id
        or confirmation.expires_at <= time.monotonic()
    ):
        telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
        return
    _clear_captcha_review_buttons(chat_id, message, telegram)
    if parts[2] == "no":
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action=confirmation.command,
            status="cancelled", operation_id=operation_id,
        )
        telegram.answer_callback_query(callback_id, "Operacion cancelada.")
        telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
        return
    telegram.answer_callback_query(callback_id, "Solicitud confirmada.")
    is_opportunity_control = confirmation.command.startswith("opportunity:")
    _record_audit_safe(
        actor=_telegram_actor(chat_id), action=confirmation.command,
        status="accepted",
        target_type="opportunity_control" if is_opportunity_control else None,
        target_id=confirmation.opportunity_target,
        operation_id=operation_id,
    )
    if is_opportunity_control:
        executor.submit(
            _execute_opportunity_control,
            confirmation,
            telegram,
            admin_api,
        )
        return
    if confirmation.command.startswith("revalidate:"):
        executor.submit(
            _execute_order_revalidation,
            confirmation,
            telegram,
            admin_api,
        )
        return
    executor.submit(
        _execute_worker_command,
        confirmation,
        telegram,
        admin_api,
    )


def _execute_order_revalidation(
    confirmation: PendingWorkerConfirmation,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    order_id = confirmation.command.removeprefix("revalidate:")
    try:
        current = admin_api.get_service_order(order_id)
        if str(current.get("preflight_status") or "") != "failed":
            telegram.send_message(
                confirmation.chat_id,
                "La orden cambio antes de confirmar y ya no requiere esa revalidacion.",
            )
            return
        admin_api.revalidate_service_order(
            order_id,
            actor=_telegram_actor(confirmation.chat_id),
        )
    except TelegramControlError as exc:
        logger.warning("Could not revalidate order from Telegram: %s", exc)
        telegram.send_message(
            confirmation.chat_id,
            "No pude iniciar la validacion. Revisa el estado y vuelve a intentarlo.",
        )
        return
    telegram.send_message(
        confirmation.chat_id,
        f"Validacion iniciada para {order_id}. Consulta el cliente en unos segundos.",
        reply_markup={
            "inline_keyboard": [[
                {"text": "Ver cliente", "callback_data": f"om:{order_id}:show"},
                {"text": "Menu", "callback_data": "ui:menu:main"},
            ]]
        },
    )


def _execute_order_change(
    change: PendingOrderChange,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    if change.action == "program_resolution":
        telegram_program_resolution.execute_resolution(
            change,
            telegram,
            admin_api,
            actor=_telegram_actor(change.chat_id),
            audit=_record_audit_safe,
            display_text=_display_text,
        )
        return
    operation_short = change.operation_id[:8]
    actor = _telegram_actor(change.chat_id)
    credentials_saved = False
    try:
        if change.action == "priority":
            current = admin_api.get_service_order(change.order_id)
            if int(current.get("priority") or 0) != int(change.original["priority"]):
                raise TelegramControlError(
                    "Order priority changed since the confirmation was prepared."
                )
            admin_api.update_order_priority(
                change.order_id,
                int(change.updated["priority"]),
                actor=actor,
            )
        elif change.action == "credentials":
            current = admin_api.get_service_order(change.order_id)
            current_details = current.get("preflight_details")
            current_error_type = (
                str(current_details.get("error_type") or "")
                if isinstance(current_details, dict)
                else ""
            )
            current_credentials = admin_api.get_service_order_credentials(change.order_id)
            current_password = str(current_credentials.get("password") or "")
            current_password_sha256 = hashlib.sha256(
                current_password.encode("utf-8")
            ).hexdigest()
            if (
                str(current.get("preflight_status") or "") != "failed"
                or current_error_type != "invalid_credentials"
                or int(current.get("preflight_cycle") or 0)
                != int(change.original["preflight_cycle"])
                or str(current_credentials.get("username") or "")
                != str(change.original["document_number"])
                or str(current_credentials.get("document_type") or "")
                != str(change.original["document_type"])
                or current_password_sha256 != change.original["password_sha256"]
            ):
                raise TelegramControlError(
                    "Order access changed since the confirmation was prepared."
                )
            admin_api.update_service_order_credentials(
                change.order_id,
                document_number=str(change.updated["document_number"]),
                document_type=str(change.updated["document_type"]),
                password=str(change.updated["password"]),
                actor=actor,
            )
            persisted_credentials = admin_api.get_service_order_credentials(change.order_id)
            if (
                str(persisted_credentials.get("username") or "")
                != str(change.updated["document_number"])
                or str(persisted_credentials.get("document_type") or "")
                != str(change.updated["document_type"])
                or str(persisted_credentials.get("password") or "")
                != str(change.updated["password"])
            ):
                raise TelegramControlError(
                    "Saved credentials do not match the requested change."
                )
            credentials_saved = True
        elif change.action in {"payment_paid", "payment_partial"}:
            current = admin_api.get_service_order(change.order_id)
            if (
                str(current.get("status") or "") != "reserved_payment_pending"
                or str(current.get("payment_status") or "") != "pending"
            ):
                raise TelegramControlError(
                    "Order is no longer a reservation with pending payment."
                )
            payment_method = (
                admin_api.record_partial_payment
                if change.action == "payment_partial"
                else admin_api.mark_payment_paid
            )
            payment_method(
                change.order_id,
                amount_paid=str(change.updated["amount_paid"]),
                amount_agreed=str(change.updated["amount_agreed"]),
                expected_amount_paid=str(change.original["amount_paid"]),
                actor=actor,
            )
        else:
            current = admin_api.get_service_order(change.order_id)
            if not all(
                current.get(field) == value
                for field, value in change.original.items()
            ):
                raise TelegramControlError(
                    "Order rules changed since the confirmation was prepared."
                )
            admin_api.update_order_rules(change.order_id, change.updated, actor=actor)
        verified = admin_api.get_service_order(change.order_id)
        if not _order_change_matches(change, verified):
            raise TelegramControlError("Saved order values do not match the requested change.")
        validation_text = ""
        if change.action == "credentials":
            verified = _wait_for_order_preflight(admin_api, change.order_id)
            preflight = str(verified.get("preflight_status") or "pending")
            if preflight == "validated":
                validation_text = "\nAcceso validado y cuenta activada."
            elif preflight == "failed":
                detail = verified.get("preflight_message") or "revisa el acceso"
                validation_text = f"\nEl nuevo acceso fue rechazado. Detalle: {detail}"
            else:
                validation_text = (
                    "\nLa nueva contrasena fue guardada. La validacion sigue en curso; "
                    "consulta el cliente en unos segundos."
                )
        elif (
            change.action == "rules"
            and str(verified.get("preflight_status") or "") != "validated"
        ):
            telegram.send_message(
                change.chat_id,
                "Restricciones guardadas. Validando ahora el acceso del cliente...",
            )
            admin_api.revalidate_service_order(change.order_id, actor=actor)
            verified = _wait_for_order_preflight(admin_api, change.order_id)
            preflight = str(verified.get("preflight_status") or "pendiente")
            if preflight == "validated":
                validation_text = "\nAcceso validado y orden activada."
            else:
                detail = verified.get("preflight_message") or "revisa el cliente"
                validation_text = f"\nValidacion: {preflight}. Detalle: {detail}"
        if change.action in {"payment_paid", "payment_partial"}:
            payment_result = (
                "Abono registrado y verificado.\nPostpago: no encolado; el cobro sigue pendiente."
                if change.action == "payment_partial"
                else "Pago registrado y verificado.\nPostpago: encolado automaticamente."
            )
            success_text = (
                f"{payment_result}\n"
                f"Solicitud: {operation_short}\n"
                f"Orden: {change.order_id}\n"
                f"Total pagado: S/{change.updated['amount_paid']}"
            )
            return_options = {
                "pending": ("Volver a pendientes", "ui:pending:1"),
                "payments": ("Volver a Por cobrar", "ui:payments:1"),
                "queue": ("Volver a Buscando cupo", "ui:queue:1"),
                "summary": ("Volver a Citas", "ui:summary:show"),
                "clients": ("Volver al historial", "ui:clients:1"),
            }
            return_label, return_callback = return_options.get(
                change.return_subject,
                ("Ver cobros pendientes", "ui:payments:1"),
            )
            success_keyboard = [
                [{"text": return_label, "callback_data": return_callback}],
                [
                    {"text": "Ver cliente", "callback_data": f"om:{change.order_id}:show"},
                    {"text": "Menu", "callback_data": "ui:menu:main"},
                ],
            ]
        else:
            success_text = (
                "Cambio aplicado y verificado.\n"
                f"Solicitud: {operation_short}\n"
                f"Orden: {change.order_id}"
                f"{validation_text}"
            )
            success_keyboard = [
                [
                    {"text": "Ver cliente", "callback_data": f"om:{change.order_id}:show"},
                    {"text": "Menu", "callback_data": "ui:menu:main"},
                ]
            ]
        telegram.send_message(
            change.chat_id,
            success_text,
            reply_markup={"inline_keyboard": success_keyboard},
        )
        logger.info(
            "Applied Telegram order change action=%s actor=%s order_id=%s",
            change.action,
            actor,
            change.order_id,
        )
        _record_audit_safe(
            actor=actor,
            action=change.action,
            status="applied",
            target_type="service_order",
            target_id=change.order_id,
            operation_id=change.operation_id,
        )
    except TelegramControlError as exc:
        logger.warning("Order change %s failed: %s", change.action, exc)
        if change.action == "credentials" and credentials_saved:
            telegram.send_message(
                change.chat_id,
                "La nueva contrasena fue guardada, pero no pude confirmar el resultado "
                "de la validacion. Abre nuevamente el cliente antes de intentar otro cambio.\n"
                f"Solicitud: {operation_short}\nOrden: {change.order_id}",
            )
            _record_audit_safe(
                actor=actor,
                action=change.action,
                status="applied",
                target_type="service_order",
                target_id=change.order_id,
                operation_id=change.operation_id,
                detail="Credentials saved; preflight follow-up could not be verified.",
            )
            return
        telegram.send_message(
            change.chat_id,
            f"No pude verificar la solicitud {operation_short}. No confirmo el cambio.",
        )
        _record_audit_safe(
            actor=actor,
            action=change.action,
            status="failed",
            target_type="service_order",
            target_id=change.order_id,
            operation_id=change.operation_id,
            detail="Admin API action could not be verified.",
        )
    except Exception:
        logger.exception("Unexpected order change execution failure")


def _execute_client_creation(
    creation: PendingClientCreation,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    actor = _telegram_actor(creation.chat_id)
    confirmation = "direct"
    try:
        created = admin_api.create_service_order(creation.values, actor=actor)
        order_id = str(created.get("order_id") or "")
        if not order_id:
            raise TelegramControlError("Admin API did not return an order_id.")
    except TelegramControlError as exc:
        reason = _client_creation_error_reason(exc)
        recovered = (
            _recover_persisted_client_creation(admin_api, creation.values)
            if reason in {
                "admin_api_timeout",
                "admin_api_unreachable",
                "admin_api_invalid_response",
            }
            else None
        )
        if recovered is None:
            logger.warning("Telegram manual client creation failed: %s", exc)
            _send_client_creation_message_safe(
                telegram,
                creation.chat_id,
                "No pude confirmar el alta. Consulta Clientes antes de volver a intentarlo.",
            )
            _record_audit_safe(
                actor=actor,
                action="client_create",
                status="failed",
                operation_id=creation.operation_id,
                detail=f"stage=create; reason={reason}",
            )
            return
        created = recovered
        order_id = str(recovered["order_id"])
        confirmation = f"recovered_after_{reason}"
        logger.warning(
            "Recovered persisted Telegram client creation after %s order_id=%s",
            reason,
            order_id,
        )

    try:
        telegram.send_message(
            creation.chat_id,
            f"CLIENTE CREADO\n\nOrden: {order_id}\nValidando el acceso al portal...",
        )
        order = _wait_for_order_preflight(admin_api, order_id)
        preflight = str(order.get("preflight_status") or "pending")
        credentials_note = ""
        try:
            credentials = admin_api.get_service_order_credentials(order_id)
        except TelegramControlError as exc:
            logger.warning("Could not reread credentials after manual creation: %s", exc)
            credentials = {}
            credentials_note = (
                "\nNota: no pude releer las credenciales desde la API; "
                "el comprobante usa los valores confirmados durante el alta."
            )
        persisted_values = {
            "document_type": credentials.get("document_type")
            or order.get("document_type")
            or creation.values.get("document_type"),
            "document_number": credentials.get("username")
            or order.get("document_number")
            or creation.values.get("document_number"),
            "password": credentials.get("password") or creation.values.get("password"),
            "contact_name": order.get("contact_name")
            or creation.values.get("contact_name"),
            "contact_source": order.get("contact_source")
            or creation.values.get("contact_source"),
            "contact_whatsapp": order.get("contact_whatsapp")
            or creation.values.get("contact_whatsapp"),
            "contact_whatsapp_username": order.get("contact_whatsapp_username")
            or creation.values.get("contact_whatsapp_username"),
            "service_type": order.get("service_type")
            or creation.values.get("service_type"),
            "reservation_price": order.get("reservation_price")
            or creation.values.get("reservation_price"),
            "minimum_reservation_date": order.get("minimum_reservation_date")
            if "minimum_reservation_date" in order
            else creation.values.get("minimum_reservation_date"),
            "maximum_reservation_date": order.get("maximum_reservation_date")
            if "maximum_reservation_date" in order
            else creation.values.get("maximum_reservation_date"),
            "allowed_weekdays": order.get("allowed_weekdays")
            if "allowed_weekdays" in order
            else creation.values.get("allowed_weekdays"),
            "excluded_date_ranges": order.get("excluded_date_ranges")
            if "excluded_date_ranges" in order
            else creation.values.get("excluded_date_ranges"),
        }
        if preflight == "validated":
            result = "Acceso correcto. La orden ya puede buscar cupos."
        elif preflight == "failed":
            result = "El acceso requiere revision. La orden quedo pausada."
        else:
            result = "La validacion sigue en curso. Consulta el cliente en unos segundos."
        telegram.send_message(
            creation.chat_id,
            _format_manual_client_details(
                persisted_values,
                title="ALTA MANUAL REGISTRADA",
            )
            + "\n\n"
            + f"Orden: {order_id}\n"
            + f"Titular del portal: {order.get('applicant_name') or 'aun no identificado'}\n"
            + f"Estado: {_order_status_label(order.get('status') or created.get('status'))}\n"
            + f"Preflight: {_preflight_status_label(preflight)}\n"
            + f"Detalle: {order.get('preflight_message') or result}"
            + credentials_note,
            reply_markup={
                "inline_keyboard": [
                    [{"text": "Ver cliente", "callback_data": f"om:{order_id}:show"}],
                    [{"text": "Menu", "callback_data": "ui:menu:main"}],
                ]
            },
        )
        persisted_password = str(persisted_values.get("password") or "")
        if persisted_password:
            sensitive_message = telegram.send_message(
                creation.chat_id,
                "CREDENCIAL TEMPORAL\n\n"
                f"Contrasena: {persisted_password}\n\n"
                "Guardala y pulsa Borrar credencial para retirarla del chat.",
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "Borrar credencial", "callback_data": "ui:delete:message"}
                    ]]
                },
            )
            sensitive_result = sensitive_message.get("result")
            sensitive_message_id = (
                sensitive_result.get("message_id")
                if isinstance(sensitive_result, dict)
                else None
            )
            if isinstance(sensitive_message_id, int):
                timer = Timer(
                    SENSITIVE_MESSAGE_TTL_SECONDS,
                    _delete_sensitive_message,
                    args=(telegram, creation.chat_id, sensitive_message_id),
                )
                timer.daemon = True
                timer.start()
        logger.info("Created service order from Telegram actor=%s order_id=%s", actor, order_id)
        _record_audit_safe(
            actor=actor,
            action="client_create",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            operation_id=creation.operation_id,
            detail=f"preflight_status={preflight}; confirmation={confirmation}",
        )
    except TelegramControlError as exc:
        reason = _client_creation_error_reason(exc)
        logger.warning(
            "Telegram client creation persisted but follow-up failed: %s",
            exc,
        )
        _send_client_creation_message_safe(
            telegram,
            creation.chat_id,
            f"El alta quedo registrada como {order_id}, pero no pude completar "
            "la comprobacion posterior. Consulta Clientes; no repitas el alta.",
        )
        _record_audit_safe(
            actor=actor,
            action="client_create",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            operation_id=creation.operation_id,
            detail=(
                f"confirmation={confirmation}; followup=incomplete; reason={reason}"
            ),
        )
    except Exception:
        logger.exception("Unexpected Telegram manual client creation failure")
        _send_client_creation_message_safe(
            telegram,
            creation.chat_id,
            f"El alta quedo registrada como {order_id}, pero ocurrio un error "
            "durante la comprobacion posterior. Consulta Clientes; no repitas el alta.",
        )
        _record_audit_safe(
            actor=actor,
            action="client_create",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            operation_id=creation.operation_id,
            detail=f"confirmation={confirmation}; followup=unexpected_error",
        )


def _delete_sensitive_message(
    telegram: TelegramBotApi,
    chat_id: str,
    message_id: int,
) -> None:
    try:
        telegram.delete_message(chat_id, message_id)
    except TelegramControlError:
        logger.warning("Could not automatically delete a sensitive Telegram message.")


def _delete_message_safe(
    telegram: TelegramBotApi,
    chat_id: str,
    message_id: Any,
) -> None:
    if not isinstance(message_id, int):
        return
    try:
        telegram.delete_message(chat_id, message_id)
    except TelegramControlError:
        logger.warning("Could not delete Telegram password input message.")


def _recover_persisted_client_creation(
    admin_api: AdminApiClient,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    document_number = str(values.get("document_number") or "").strip()
    if not document_number:
        return None
    try:
        candidates = admin_api.search_service_orders(document_number)
    except TelegramControlError as exc:
        logger.warning("Could not verify persisted Telegram client creation: %s", exc)
        return None

    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        if str(candidate.get("document_number") or "").strip() != document_number:
            continue
        if candidate.get("parent_order_id") or candidate.get("program_expediente"):
            continue
        if candidate.get("program_plate"):
            continue
        order_id = str(candidate.get("order_id") or "").strip()
        if not order_id:
            continue
        try:
            credentials = admin_api.get_service_order_credentials(order_id)
        except TelegramControlError as exc:
            logger.warning(
                "Could not verify credentials for recovered order_id=%s: %s",
                order_id,
                exc,
            )
            continue
        if not _persisted_client_creation_matches(values, candidate, credentials):
            continue
        matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _persisted_client_creation_matches(
    values: dict[str, Any],
    order: dict[str, Any],
    credentials: dict[str, Any],
) -> bool:
    expected_credentials = {
        "username": str(values.get("document_number") or "").strip(),
        "document_type": str(values.get("document_type") or "").strip(),
        "password": str(values.get("password") or ""),
    }
    if any(credentials.get(field) != expected for field, expected in expected_credentials.items()):
        return False

    comparable_fields = (
        "contact_name",
        "contact_source",
        "contact_whatsapp",
        "contact_whatsapp_username",
        "service_type",
        "service_package",
        "reservation_price",
        "minimum_reservation_date",
        "maximum_reservation_date",
        "allowed_weekdays",
        "excluded_date_ranges",
    )
    return all(
        field not in values
        or values[field] is None
        or order.get(field) == values[field]
        for field in comparable_fields
    )


def _client_creation_error_reason(exc: TelegramControlError) -> str:
    if str(exc).startswith("Telegram "):
        return "telegram_delivery_error"
    cause = exc.__cause__
    nested_reason = getattr(cause, "reason", None)
    if isinstance(cause, TimeoutError) or isinstance(nested_reason, TimeoutError):
        return "admin_api_timeout"
    if isinstance(cause, HTTPError):
        return f"admin_api_http_{cause.code}"
    if isinstance(cause, URLError):
        return "admin_api_unreachable"
    if "did not return an order_id" in str(exc) or "invalid JSON" in str(exc):
        return "admin_api_invalid_response"
    return "admin_api_confirmation_error"


def _send_client_creation_message_safe(
    telegram: TelegramBotApi,
    chat_id: str,
    message: str,
) -> bool:
    try:
        telegram.send_message(chat_id, message)
    except TelegramControlError as exc:
        logger.warning("Could not send Telegram client creation status: %s", exc)
        return False
    return True


def _wait_for_order_preflight(
    admin_api: AdminApiClient, order_id: str
) -> dict[str, Any]:
    deadline = time.monotonic() + WORKER_COMMAND_TIMEOUT_SECONDS
    last_order: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_order = admin_api.get_service_order(order_id)
        if str(last_order.get("preflight_status") or "") not in {
            "",
            "pending",
            "running",
        }:
            return last_order
        time.sleep(2)
    return last_order


def _order_change_matches(change: PendingOrderChange, order: dict[str, Any]) -> bool:
    if change.action == "credentials":
        return (
            int(order.get("preflight_cycle") or 0)
            > int(change.original.get("preflight_cycle") or 0)
            and str(order.get("preflight_status") or "")
            in {"pending", "running", "validated", "failed"}
        )
    if change.action == "payment_partial":
        return (
            str(order.get("status") or "") == "reserved_payment_pending"
            and str(order.get("payment_status") or "") == "pending"
            and _money_value(order.get("amount_paid"))
            == _money_value(change.updated.get("amount_paid"))
            and _money_value(order.get("amount_agreed"))
            == _money_value(change.updated.get("amount_agreed"))
        )
    if change.action == "payment_paid":
        return (
            str(order.get("status") or "") == "paid"
            and str(order.get("payment_status") or "") == "paid"
            and _money_value(order.get("amount_paid"))
            == _money_value(change.updated.get("amount_paid"))
            and _money_value(order.get("amount_agreed"))
            == _money_value(change.updated.get("amount_agreed"))
        )
    return all(order.get(field) == value for field, value in change.updated.items())


def _execute_opportunity_control(
    confirmation: PendingWorkerConfirmation,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    actor = _telegram_actor(confirmation.chat_id)
    action = confirmation.command.removeprefix("opportunity:")
    target = confirmation.opportunity_target
    revision = confirmation.expected_revision
    if target not in {"obs006", "obs007"} or revision is None or confirmation.reason is None:
        logger.error(
            "Incomplete opportunity confirmation operation_id=%s",
            confirmation.operation_id,
        )
        return
    try:
        current = admin_api.get_opportunity_control()
        if current.get("revision") != revision:
            telegram.send_message(
                confirmation.chat_id,
                "El control cambio antes de aplicar la solicitud. No se modifico nada.",
            )
            _record_audit_safe(
                actor=actor,
                action=confirmation.command,
                status="failed",
                target_type="opportunity_control",
                target_id=target,
                operation_id=confirmation.operation_id,
                detail="stale_revision",
            )
            _send_opportunity_panel(confirmation.chat_id, telegram, admin_api)
            return
        result = admin_api.update_opportunity_control(
            action=action,
            target=target,
            reason=confirmation.reason,
            expected_revision=revision,
            actor=actor,
        )
        telegram.send_message(
            confirmation.chat_id,
            str(result.get("message") or "Control de oportunidad actualizado."),
        )
        _record_audit_safe(
            actor=actor,
            action=confirmation.command,
            status="applied",
            target_type="opportunity_control",
            target_id=target,
            operation_id=confirmation.operation_id,
            detail=f"revision={result.get('revision', 'unknown')}",
        )
        _send_opportunity_panel(confirmation.chat_id, telegram, admin_api)
    except TelegramControlError as exc:
        stale = "HTTP 409" in str(exc)
        logger.warning("Opportunity control %s failed: %s", action, exc)
        telegram.send_message(
            confirmation.chat_id,
            (
                "El estado cambio o la operacion ya no es segura. Revisa el panel actualizado."
                if stale
                else "No pude aplicar el control de oportunidad. No confirmo cambios."
            ),
        )
        _record_audit_safe(
            actor=actor,
            action=confirmation.command,
            status="failed",
            target_type="opportunity_control",
            target_id=target,
            operation_id=confirmation.operation_id,
            detail="stale_or_unsafe" if stale else "admin_api_error",
        )
        if stale:
            _send_opportunity_panel(confirmation.chat_id, telegram, admin_api)


def _execute_worker_command(
    confirmation: PendingWorkerConfirmation,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    operation_short = confirmation.operation_id[:8]
    actor = _telegram_actor(confirmation.chat_id)
    try:
        queued = admin_api.enqueue_worker_command(confirmation.command, actor=actor)
        command_id = queued.get("command_id")
        if not isinstance(command_id, str) or not command_id:
            raise TelegramControlError("Admin API did not return a command_id.")
        telegram.send_message(
            confirmation.chat_id,
            f"Solicitud {operation_short} encolada. Verificando resultado real...",
        )
        command = _wait_for_worker_command(admin_api, command_id)
        status = command.get("status")
        if status != "applied":
            detail = "fallo" if status == "failed" else "no termino a tiempo"
            telegram.send_message(
                confirmation.chat_id,
                f"La solicitud {operation_short} {detail}. No confirmo el cambio.",
            )
            _record_audit_safe(
                actor=actor,
                action=confirmation.command,
                status="failed",
                operation_id=confirmation.operation_id,
                detail=f"worker_command_status={status or 'unknown'}",
            )
            return
        worker = _wait_for_worker_effect(admin_api, confirmation.command)
        telegram.send_message(
            confirmation.chat_id,
            _format_worker_command_success(confirmation.command, operation_short, worker),
        )
        _record_audit_safe(
            actor=actor,
            action=confirmation.command,
            status="applied",
            operation_id=confirmation.operation_id,
            detail=f"worker_phase={worker.get('phase') or 'unknown'}",
        )
    except TelegramControlError as exc:
        logger.warning("Worker command %s failed: %s", confirmation.command, exc)
        try:
            telegram.send_message(
                confirmation.chat_id,
                f"No pude completar la solicitud {operation_short}. El cambio no fue confirmado.",
            )
        except TelegramControlError:
            logger.warning("Could not deliver the worker command failure message.")
        _record_audit_safe(
            actor=actor,
            action=confirmation.command,
            status="failed",
            operation_id=confirmation.operation_id,
            detail="Worker command could not be completed.",
        )
    except Exception:
        logger.exception("Unexpected worker command execution failure")


def _wait_for_worker_command(
    admin_api: AdminApiClient,
    command_id: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + WORKER_COMMAND_TIMEOUT_SECONDS
    last_command: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_command = admin_api.get_worker_command(command_id)
        if last_command is not None and last_command.get("status") in {"applied", "failed"}:
            return last_command
        time.sleep(1)
    return last_command or {"status": "timeout"}


def _wait_for_worker_effect(admin_api: AdminApiClient, command: str) -> dict[str, Any]:
    deadline = time.monotonic() + WORKER_COMMAND_TIMEOUT_SECONDS
    last_worker: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last_worker = admin_api.get_worker()
        except TelegramControlError:
            time.sleep(1)
            continue
        paused = bool(last_worker.get("paused"))
        running = bool(last_worker.get("worker_running"))
        phase = str(last_worker.get("phase") or "")
        if command == "pause" and paused:
            return last_worker
        if command == "resume" and running and not paused:
            return last_worker
        if command == "restart" and running and phase != "restarting":
            return last_worker
        time.sleep(1)
    raise TelegramControlError("Worker state did not reach the expected result.")


def _format_worker_command_success(
    command: str,
    operation_id: str,
    worker: dict[str, Any],
) -> str:
    phase = str(worker.get("phase") or "desconocida")
    if command == "pause":
        result = "Worker pausado correctamente."
    elif command == "resume":
        result = "Worker reanudado correctamente."
    else:
        result = "Worker reiniciado y recuperado correctamente."
    return f"{result}\nSolicitud: {operation_id}\nFase actual: {phase}"


def _worker_command_label(command: str) -> str:
    return {
        "pause": "pausar el worker",
        "resume": "reanudar el worker",
        "restart": "reiniciar el worker",
    }[command]


def _telegram_actor(chat_id: str, user_id: str | None = None) -> str:
    effective_user_id = user_id or chat_id
    identity = f"chat:{chat_id}|user:{effective_user_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"telegram:{digest}"


def _audit_target(arguments: str) -> str | None:
    candidate = arguments.strip().split(maxsplit=1)[0] if arguments.strip() else ""
    return candidate if _valid_order_id(candidate) else None


def _record_audit_safe(
    *,
    actor: str,
    action: str,
    status: str,
    target_type: str | None = None,
    target_id: str | None = None,
    operation_id: str | None = None,
    detail: str | None = None,
) -> None:
    try:
        record_remote_control_audit(
            actor=actor,
            action=action,
            status=status,
            target_type=target_type,
            target_id=target_id,
            operation_id=operation_id,
            detail=detail,
        )
    except Exception:
        logger.warning("Could not persist remote-control audit action=%s", action)


def _cancel_chat_confirmations(
    chat_id: str,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        return _cancel_chat_confirmations_unlocked(chat_id, pending_confirmations)


def _cancel_chat_confirmations_unlocked(
    chat_id: str,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
) -> bool:
    operation_ids = [
        operation_id
        for operation_id, confirmation in pending_confirmations.items()
        if confirmation.chat_id == chat_id
    ]
    for operation_id in operation_ids:
        pending_confirmations.pop(operation_id, None)
    return bool(operation_ids)


def _cancel_pending_client_creation_unlocked(
    chat_id: str,
    pending_creations: dict[str, PendingClientCreation],
) -> bool:
    operation_ids = [
        operation_id
        for operation_id, creation in pending_creations.items()
        if creation.chat_id == chat_id
    ]
    for operation_id in operation_ids:
        pending_creations.pop(operation_id, None)
    return bool(operation_ids)


def _remove_expired_confirmations(
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    confirmation_lock: Lock,
) -> None:
    now = time.monotonic()
    with confirmation_lock:
        expired = [
            operation_id
            for operation_id, confirmation in pending_confirmations.items()
            if confirmation.expires_at <= now
        ]
        for operation_id in expired:
            pending_confirmations.pop(operation_id, None)


def _cancel_chat_order_state(
    chat_id: str,
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        return _cancel_chat_order_state_unlocked(
            chat_id,
            pending_order_changes,
            rules_conversations,
        )


def _cancel_chat_order_state_unlocked(
    chat_id: str,
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
) -> bool:
    operation_ids = [
        operation_id
        for operation_id, change in pending_order_changes.items()
        if change.chat_id == chat_id
    ]
    for operation_id in operation_ids:
        pending_order_changes.pop(operation_id, None)
    conversation_removed = rules_conversations.pop(chat_id, None) is not None
    return bool(operation_ids) or conversation_removed


def _remove_expired_order_state(
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
    confirmation_lock: Lock,
) -> None:
    now = time.monotonic()
    with confirmation_lock:
        expired_changes = [
            operation_id
            for operation_id, change in pending_order_changes.items()
            if change.expires_at <= now
        ]
        for operation_id in expired_changes:
            pending_order_changes.pop(operation_id, None)
        expired_chats = [
            chat_id
            for chat_id, conversation in rules_conversations.items()
            if conversation.expires_at <= now
        ]
        for chat_id in expired_chats:
            rules_conversations.pop(chat_id, None)


def _cancel_chat_client_state(
    chat_id: str,
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        removed = conversations.pop(chat_id, None) is not None
        return _cancel_pending_client_creation_unlocked(
            chat_id,
            pending_creations,
        ) or removed


def _remove_expired_client_state(
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    telegram: TelegramBotApi,
    confirmation_lock: Lock,
) -> None:
    now = time.monotonic()
    with confirmation_lock:
        expired_chats = [
            chat_id
            for chat_id, conversation in conversations.items()
            if conversation.expires_at <= now
        ]
        for chat_id in expired_chats:
            conversations.pop(chat_id, None)
        expired_operations = [
            operation_id
            for operation_id, creation in pending_creations.items()
            if creation.expires_at <= now
        ]
        expired_confirmation_chats = {
            pending_creations[operation_id].chat_id
            for operation_id in expired_operations
        }
        for operation_id in expired_operations:
            pending_creations.pop(operation_id, None)
    for chat_id in expired_chats:
        telegram.send_message(
            chat_id,
            "El alta manual vencio por inactividad. No se creo ni guardo nada.",
            reply_markup=_main_menu_markup(),
        )
    for chat_id in expired_confirmation_chats:
        telegram.send_message(
            chat_id,
            "La confirmacion vencio. No se creo ni guardo ningun cliente.",
            reply_markup=_main_menu_markup(),
        )


def _remove_expired_captcha_state(
    conversations: dict[str, CaptchaReviewConversation],
    telegram: TelegramBotApi,
) -> None:
    now = time.monotonic()
    expired_chats = [
        chat_id
        for chat_id, conversation in conversations.items()
        if conversation.expires_at <= now
    ]
    for chat_id in expired_chats:
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "La sesion de CAPTCHA vencio despues de 10 minutos sin actividad.",
            reply_markup=_main_menu_markup(),
        )


def format_worker_status(payload: dict[str, Any]) -> str:
    worker_running = bool(payload.get("worker_running"))
    phase = str(payload.get("phase") or "desconocida")
    paused = bool(payload.get("paused"))
    if worker_running and phase == "outside_hot_window":
        summary = "Activo, esperando la siguiente ventana de trabajo."
    elif worker_running and paused:
        summary = "Activo, pero pausado administrativamente."
    elif worker_running:
        summary = "Activo."
    else:
        summary = "Worker sin lease activo; el supervisor deberia recuperarlo."
    lines = [
        "ESTADO DEL SISTEMA",
        "",
        summary,
        f"Fase: {phase}",
        f"Pausado: {'si' if paused else 'no'}",
    ]
    current_order = payload.get("current_order_id")
    if current_order:
        lines.append(f"Orden actual: {current_order}")
    last_check = _format_lima_datetime(payload.get("last_check_at"))
    next_check = _format_lima_datetime(payload.get("next_check_at"))
    if last_check:
        lines.append(f"Ultima revision: {last_check}")
    if next_check:
        lines.append(f"Proxima revision: {next_check}")
    errors = int(payload.get("consecutive_errors") or 0)
    lines.append(f"Errores consecutivos: {errors}")
    if payload.get("last_error"):
        lines.append("Ultimo error: disponible en el dashboard.")
    return "\n".join(lines)


def _command_parts(text: str) -> tuple[str | None, str]:
    stripped = text.strip()
    first, separator, arguments = stripped.partition(" ")
    if not first.startswith("/"):
        return None, ""
    command = first[1:].split("@", maxsplit=1)[0].strip().lower() or None
    return command, arguments.strip() if separator else ""


def _format_lima_datetime(value: Any) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(LIMA_TIMEZONE).strftime("%d-%m-%Y %H:%M:%S")
    except ValueError:
        return None


def _update_id(update: dict[str, Any]) -> int | None:
    value = update.get("update_id")
    return value if isinstance(value, int) and value >= 0 else None


def _load_next_offset(path: Path) -> int | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("next_offset")
        return value if isinstance(value, int) and value >= 0 else None
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        logger.warning("Ignoring an invalid Telegram control offset file.")
        return None


def _store_next_offset(path: Path, next_offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps({"next_offset": next_offset}) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json_response(response: Any) -> dict[str, Any]:
    body = response.read(MAX_TELEGRAM_RESPONSE_BYTES + 1)
    if len(body) > MAX_TELEGRAM_RESPONSE_BYTES:
        raise TelegramControlError("Remote response is too large.")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramControlError("Remote service returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise TelegramControlError("Remote service returned an invalid object.")
    return data


def _multipart_form_data(
    boundary: str,
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, str, bytes]],
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    for name, (filename, content_type, content) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks)


def _positive_int(value: str | None, *, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise TelegramControlError(f"Invalid positive integer: {value!r}") from exc
    if parsed < 1:
        raise TelegramControlError(f"Integer must be positive: {value!r}")
    return parsed


def _install_signal_handlers(stop_event: Event) -> None:
    def request_stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        signal_value = getattr(signal, signal_name, None)
        if signal_value is not None:
            signal.signal(signal_value, request_stop)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Telegram remote-control receiver.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate Telegram and Admin API connectivity without consuming updates.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        raise SystemExit(run_control(check_only=args.check))
    except TelegramControlError as exc:
        logger.error("Telegram control could not start: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
