from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import secrets
import signal
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from threading import Event, Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings, load_settings
from appointment_bot.db.remote_control_audit import record_remote_control_audit
from appointment_bot.services.logger import setup_logging
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)

LIMA_TIMEZONE = ZoneInfo("America/Lima")
DEFAULT_ADMIN_API_URL = "http://127.0.0.1:8766"
DEFAULT_POLL_TIMEOUT_SECONDS = 30
RETRY_DELAY_SECONDS = 5
CONFIRMATION_TTL_SECONDS = 120
CONVERSATION_TTL_SECONDS = 300
NEW_CLIENT_CONVERSATION_TTL_SECONDS = 60
NEW_CLIENT_CONFIRMATION_TTL_SECONDS = 60
WORKER_COMMAND_TIMEOUT_SECONDS = 90
MAX_TELEGRAM_RESPONSE_BYTES = 1024 * 1024
CLIENTS_PAGE_SIZE = 8
GENERAL_RATE_LIMIT = 30
MUTATION_RATE_LIMIT = 15
RATE_LIMIT_WINDOW_SECONDS = 60
MUTATING_COMMANDS = {
    "cliente_nuevo",
    "pausar",
    "prioridad",
    "reanudar",
    "reglas_editar",
    "reiniciar",
}
ORDER_TARGET_COMMANDS = {
    "cliente",
    "credenciales",
    "prioridad",
    "reglas",
    "reglas_editar",
}
HELP_TEXT = """Control remoto disponible:

/estado - Estado real del worker
/clientes [pagina] - Resumen paginado de la cola
/cliente ORDER_ID - Detalle operativo enmascarado
/reglas ORDER_ID - Restricciones de una orden
/ultimos_errores - Incidentes operativos recientes
/prioridad ORDER_ID VALOR - Cambiar prioridad con confirmacion
/reglas_editar ORDER_ID - Editar restricciones paso a paso
/cliente_nuevo - Registrar manualmente un cliente
/pausar - Pausar el worker con confirmacion
/reanudar - Reanudar el worker con confirmacion
/reiniciar - Reiniciar el worker con confirmacion
/ayuda - Mostrar esta ayuda
/cancelar - Cancelar la operacion guiada actual
/menu - Abrir el menu principal con botones
/buscar TEXTO - Buscar cliente u orden
/resumen - Resumen operativo del dia
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


@dataclass(frozen=True)
class PendingWorkerConfirmation:
    operation_id: str
    chat_id: str
    command: str
    expires_at: float


@dataclass(frozen=True)
class PendingOrderChange:
    operation_id: str
    chat_id: str
    action: str
    order_id: str
    original: dict[str, Any]
    updated: dict[str, Any]
    expires_at: float


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


class AdminApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get_worker(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/worker")

    def get_service_orders(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/service-orders")
        orders = payload.get("service_orders", [])
        if not isinstance(orders, list):
            raise TelegramControlError("Admin API returned an invalid service order list.")
        return [item for item in orders if isinstance(item, dict)]

    def get_service_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/service-orders/{quote(order_id, safe='')}")

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

    def create_service_order(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/service-orders",
            payload=values,
            actor=actor,
        )

    def get_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/v1/runs?limit={limit}")
        runs = payload.get("runs", [])
        if not isinstance(runs, list):
            raise TelegramControlError("Admin API returned an invalid run list.")
        return [item for item in runs if isinstance(item, dict)]

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

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if actor:
            headers["X-Appointment-Actor"] = actor
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
            with urlopen(request, timeout=5) as response:
                return _read_json_response(response)
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

    def delete_message(self, chat_id: str, message_id: int) -> None:
        self._request(
            "deleteMessage",
            {"chat_id": chat_id, "message_id": str(message_id)},
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
        admin_api_url=os.getenv("TELEGRAM_CONTROL_ADMIN_API_URL", DEFAULT_ADMIN_API_URL).strip(),
        admin_api_token=admin_api_token,
        offset_path=offset_path,
        poll_timeout_seconds=poll_timeout,
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
    recent_orders: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=8))
    rate_limiter = TelegramRateLimiter()
    confirmation_lock = Lock()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="telegram-worker-command")
    _record_audit_safe(actor="telegram-control", action="receiver", status="started")
    _send_startup_notice(config, telegram, worker)
    logger.info("Telegram control long polling started.")
    try:
        while not stop_event.is_set():
            try:
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
        if not rate_limiter.allow(chat_id, mutation=True):
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
        search = search_conversations.pop(chat_id, None)
        if search is not None:
            if search.expires_at <= time.monotonic():
                telegram.send_message(
                    chat_id,
                    "La busqueda vencio. Pulsa Buscar para intentar otra vez.",
                )
                return
            _send_search_results(chat_id, text, telegram, admin_api)
            return
        if _process_new_client_message(
            chat_id,
            text,
            telegram,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        ):
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
        return
    mutation = command in MUTATING_COMMANDS
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
        actor=_telegram_actor(chat_id),
        action=command,
        status="accepted",
        target_type="service_order" if audit_target else None,
        target_id=audit_target,
    )
    if command in {"menu", "start"}:
        _send_main_menu(chat_id, telegram)
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
        response = (
            "Operacion pendiente cancelada."
            if removed or order_removed or client_removed or search_removed
            else "No hay una operacion guiada activa."
        )
        telegram.send_message(chat_id, response)
        return
    if command == "estado":
        _send_worker_panel(chat_id, telegram, admin_api)
        return
    if command == "clientes":
        _send_clients(chat_id, arguments, telegram, admin_api)
        return
    if command == "buscar":
        _send_search_results(chat_id, arguments, telegram, admin_api)
        return
    if command == "recientes":
        _send_recent_orders(chat_id, telegram, admin_api, recent_orders)
        return
    if command == "resumen":
        _send_daily_summary(chat_id, telegram, admin_api)
        return
    if command in {"cliente", "reglas"}:
        _send_order_query(chat_id, command, arguments, telegram, admin_api)
        return
    if command == "credenciales":
        _send_credentials(chat_id, arguments, telegram, admin_api)
        return
    if command == "cliente_nuevo":
        search_conversations.pop(chat_id, None)
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
    if command == "reglas_editar":
        search_conversations.pop(chat_id, None)
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


def _main_menu_markup() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Clientes", "callback_data": "ui:clients:1"},
                {"text": "Alta manual", "callback_data": "ui:manual:start"},
            ],
            [{"text": "Buscar cliente", "callback_data": "ui:search:start"}],
            [
                {"text": "Estado del bot", "callback_data": "ui:status:show"},
                {"text": "Resumen de hoy", "callback_data": "ui:summary:show"},
            ],
            [
                {"text": "Sistema y errores", "callback_data": "ui:worker:show"},
            ],
        ]
    }


def _send_main_menu(chat_id: str, telegram: TelegramBotApi) -> None:
    telegram.send_message(
        chat_id,
        "MENU PRINCIPAL\n\nElige una accion. No necesitas recordar comandos.",
        reply_markup=_main_menu_markup(),
    )


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
        if not order_id or len(f"om:{order_id}:show".encode()) > 64:
            continue
        label = _applicant_display_name(order)
        if label == "Titular no identificado por el portal":
            label = str(order.get("contact_name") or order_id)
        keyboard.append(
            [{"text": _display_text(label, 34), "callback_data": f"om:{order_id}:show"}]
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
        ("Baja", 0),
        ("Normal", 10),
        ("Alta", 50),
        ("Urgente", 100),
    ]
    telegram.send_message(
        chat_id,
        f"PRIORIDAD\n\nOrden: {order_id}\nValor actual: {current}\n\nElige un valor:",
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": label, "callback_data": f"pq:{order_id}:{value}"}
                    for label, value in presets[:2]
                ],
                [
                    {"text": label, "callback_data": f"pq:{order_id}:{value}"}
                    for label, value in presets[2:]
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


def _send_order_panel(
    chat_id: str,
    order_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    recent_orders: dict[str, deque[str]],
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
        keyboard.append([{
            "text": "Reintentar validacion",
            "callback_data": f"om:{order_id}:validate",
        }])
    keyboard.extend(
        [
            [{"text": "Actualizar", "callback_data": f"om:{order_id}:show"}],
            [
                {"text": "Clientes", "callback_data": "ui:clients:1"},
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
            "callback_data": f"om:{order.get('order_id')}:show",
        }]
        for order in matches
        if len(f"om:{order.get('order_id')}:show".encode()) <= 64
    ]
    keyboard.append([{"text": "Menu", "callback_data": "ui:menu:main"}])
    telegram.send_message(
        chat_id,
        f"BUSQUEDA: {arguments.strip()}\n\n"
        + (f"Coincidencias: {len(matches)}" if matches else "No encontre coincidencias."),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_recent_orders(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    recent_orders: dict[str, deque[str]],
) -> None:
    order_ids = list(recent_orders.get(chat_id, ()))
    if not order_ids:
        telegram.send_message(
            chat_id,
            "Aun no consultaste clientes desde este inicio del receptor.",
            reply_markup={
                "inline_keyboard": [[{"text": "Clientes", "callback_data": "ui:clients:1"}]]
            },
        )
        return
    try:
        orders = {str(item.get("order_id")): item for item in admin_api.get_service_orders()}
    except TelegramControlError as exc:
        logger.warning("Could not read recent service orders: %s", exc)
        telegram.send_message(chat_id, "No pude consultar los clientes recientes.")
        return
    keyboard = []
    for order_id in order_ids:
        order = orders.get(order_id, {})
        label = _applicant_display_name(order) if order else order_id
        if label == "Titular no identificado por el portal":
            label = str(order.get("contact_name") or order_id)
        keyboard.append([
            {"text": _display_text(label, 36), "callback_data": f"om:{order_id}:show"}
        ])
    keyboard.append([{"text": "Menu", "callback_data": "ui:menu:main"}])
    telegram.send_message(
        chat_id,
        "CLIENTES RECIENTES",
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_daily_summary(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        worker = admin_api.get_worker()
        orders = admin_api.get_service_orders()
    except TelegramControlError as exc:
        logger.warning("Could not prepare daily summary: %s", exc)
        telegram.send_message(chat_id, "No pude preparar el resumen de hoy.")
        return
    today = datetime.now(LIMA_TIMEZONE).date().isoformat()
    reserved_today = sum(1 for order in orders if str(order.get("reservation_date") or "") == today)
    counts = _order_status_counts(orders)
    lines = [
        "RESUMEN DE HOY",
        "",
        f"Fecha: {_format_operator_date(today)}",
        f"Worker: {'activo' if worker.get('worker_running') else 'sin confirmar'}",
        f"Fase: {worker.get('phase') or 'desconocida'}",
        f"Clientes activos: {counts['active']}",
        f"Pausados: {counts['paused']}",
        f"Reservas de hoy: {reserved_today}",
        f"Pendientes de pago: {counts['payment_pending']}",
        f"Errores consecutivos: {worker.get('consecutive_errors') or 0}",
    ]
    telegram.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup={
            "inline_keyboard": [[
                {"text": "Actualizar", "callback_data": "ui:summary:show"},
                {"text": "Menu", "callback_data": "ui:menu:main"},
            ]]
        },
    )


def _send_credentials(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    order_id = arguments.strip()
    if not _valid_order_id(order_id):
        telegram.send_message(chat_id, "Uso: /credenciales ORDER_ID")
        return
    try:
        credentials = admin_api.get_service_order_credentials(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not read credentials for order %s: %s", order_id, exc)
        telegram.send_message(chat_id, "No pude consultar las credenciales de esa orden.")
        return
    telegram.send_message(
        chat_id,
        "CREDENCIALES DEL PORTAL\n\n"
        f"Orden: {credentials.get('order_id') or order_id}\n"
        f"Tipo: {credentials.get('document_type') or 'no disponible'}\n"
        f"Usuario / documento: {credentials.get('username') or 'no disponible'}\n"
        f"Contrasena: {credentials.get('password') or 'no disponible'}\n\n"
        "Mensaje sensible: quedara en el historial de este chat.",
        reply_markup={
            "inline_keyboard": [
                [{"text": "Eliminar este mensaje", "callback_data": "ui:delete:message"}],
                [{"text": "Volver al cliente", "callback_data": f"om:{order_id}:show"}],
            ]
        },
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
        "Las credenciales quedaran en el historial de este chat. "
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
        telegram.send_message(chat_id, str(exc))
        return True
    conversation.expires_at = time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS
    if prompt is not None:
        telegram.send_message(
            chat_id,
            f"{prompt}\nTienes 60 segundos para completar este paso.",
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
        keyboard = [[{
            "text": "Omitir WhatsApp",
            "callback_data": f"nf:{session_id}:phone_omit",
        }]]
    elif step == 6:
        keyboard = [[
            {"text": "Sin restricciones", "callback_data": f"nf:{session_id}:rules_none"},
            {"text": "Configurar", "callback_data": f"nf:{session_id}:rules_yes"},
        ]]
    elif step in {7, 8}:
        keyboard = [[{
            "text": "Sin limite",
            "callback_data": f"nf:{session_id}:value_clear",
        }]]
    elif step == 9:
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
    elif step == 10:
        keyboard = [[{
            "text": "Sin exclusiones",
            "callback_data": f"nf:{session_id}:value_clear",
        }]]
    else:
        keyboard = []
    keyboard.append([{"text": "Cancelar", "callback_data": "ui:cancel:guided"}])
    return {"inline_keyboard": keyboard}


def _apply_new_client_value(
    conversation: NewClientConversation, value: str
) -> str | None:
    return _apply_manual_client_value(conversation, value)


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
        if normalized.lower() not in {"omitir", "sin whatsapp"}:
            if normalized.startswith("@"):
                if not re.fullmatch(r"@\S{1,99}", normalized):
                    raise ValueError("Usuario invalido. Usa el formato @usuario.")
                conversation.values["contact_whatsapp_username"] = normalized
            else:
                phone = re.sub(r"[\s()-]", "", normalized)
                if not re.fullmatch(r"\+?\d{8,15}", phone):
                    raise ValueError(
                        "WhatsApp invalido. Usa un numero, @usuario o elige Omitir."
                    )
                conversation.values["contact_whatsapp"] = phone
    elif step == 6:
        choice = normalized.lower().replace(" ", "_")
        if choice == "sin_restricciones":
            conversation.step += 1
            return None
        if choice not in {"con_restricciones", "configurar"}:
            raise ValueError("Elige Sin restricciones o Configurar.")
        conversation.values.update(
            {
                "minimum_reservation_date": None,
                "maximum_reservation_date": None,
                "allowed_weekdays": None,
                "excluded_date_ranges": [],
            }
        )
    else:
        field, parsed_value = _parse_rules_step(step - 7, normalized, conversation.values)
        conversation.values[field] = parsed_value
        if step == 8:
            _validate_rules_payload(conversation.values)
        if step == 10:
            _validate_rules_payload(conversation.values)
    conversation.step += 1
    return _manual_client_step_prompt(conversation.step)


def _manual_client_step_prompt(step: int) -> str | None:
    prompts = {
        1: "Paso 2: escribe el numero de documento.",
        2: "Paso 3: escribe la contrasena del portal.",
        3: "Paso 4: escribe el nombre de la persona de contacto.",
        4: "Paso 5: elige de donde llego el cliente.",
        5: "Paso 6: escribe el numero de WhatsApp, @usuario o elige Omitir.",
        6: "Paso 7: indica si deseas configurar restricciones ahora.",
        7: "Restriccion 1 de 4: fecha minima en DD-MM-YYYY o Sin limite.",
        8: "Restriccion 2 de 4: fecha maxima en DD-MM-YYYY o Sin limite.",
        9: "Restriccion 3 de 4: elige los dias permitidos o escribe 1,2,...7.",
        10: (
            "Restriccion 4 de 4: fechas excluidas en DD-MM-YYYY al DD-MM-YYYY; "
            "separa varios rangos con ; o elige Sin exclusiones."
        ),
    }
    return prompts.get(step)


def _format_new_client_confirmation(values: dict[str, Any]) -> str:
    return (
        _format_manual_client_details(values, title="CONFIRMAR ALTA MANUAL")
        + "\n\nRevisa todos los datos antes de crear el cliente. "
        "La confirmacion vence en 60 segundos."
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
            f"Contrasena: {values.get('password') or 'no disponible'}",
            f"Contacto: {values.get('contact_name') or 'no disponible'}",
            f"Fuente: {values.get('contact_source') or 'no disponible'}",
            "WhatsApp: "
            + str(
                values.get("contact_whatsapp")
                or values.get("contact_whatsapp_username")
                or "no registrado"
            ),
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
        f"Documento: {order.get('document_number') or 'no disponible'}",
        "",
        f"Contacto: {contact_name}",
        "WhatsApp: "
        + str(
            order.get("contact_whatsapp")
            or order.get("contact_whatsapp_username")
            or "no registrado"
        ),
        f"Fuente: {order.get('contact_source') or 'no registrada'}",
        "",
        f"Estado: {_order_status_label(order.get('status'))}",
        f"Validacion: {_preflight_status_label(order.get('preflight_status'))}",
        f"Prioridad: {order.get('priority', 0)}",
        f"Reserva: {order.get('reservation_status') or 'sin reserva'}",
        f"Pago: {order.get('payment_status') or 'sin pago'}",
    ]
    if order.get("reservation_date") or order.get("reservation_hour"):
        lines.append(
            "Cita: "
            f"{order.get('reservation_date') or 'sin fecha'} "
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


def _phone_digits(value: Any) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits[-9:] if len(digits) >= 9 else digits


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
    recent_orders: dict[str, deque[str]],
    confirmation_lock: Lock,
) -> bool:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in {"ui", "om", "pq", "wk", "nf", "rf"}:
        return False
    prefix, subject, action = parts
    telegram.answer_callback_query(callback_id, "Procesando...")
    if prefix == "ui":
        if subject == "menu":
            _send_main_menu(chat_id, telegram)
        elif subject == "status":
            _send_worker_panel(chat_id, telegram, admin_api)
        elif subject == "clients":
            _send_clients(chat_id, action, telegram, admin_api)
        elif subject == "manual":
            search_conversations.pop(chat_id, None)
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
        elif subject == "summary":
            _send_daily_summary(chat_id, telegram, admin_api)
        elif subject == "recent":
            _send_recent_orders(chat_id, telegram, admin_api, recent_orders)
        elif subject == "worker":
            _send_worker_panel(chat_id, telegram, admin_api)
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
            telegram.send_message(
                chat_id,
                "Operacion cancelada." if removed else "No habia una operacion activa.",
                reply_markup=_main_menu_markup(),
            )
        else:
            telegram.send_message(chat_id, "Accion de menu no reconocida.")
        return True
    if prefix == "om":
        order_id = subject
        if not _valid_order_id(order_id):
            telegram.send_message(chat_id, "La orden seleccionada no es valida.")
        elif action == "show":
            _send_order_panel(chat_id, order_id, telegram, admin_api, recent_orders)
        elif action == "credentials":
            _send_credentials(chat_id, order_id, telegram, admin_api)
        elif action == "rules":
            _send_order_query(chat_id, "reglas", order_id, telegram, admin_api)
        elif action == "priority":
            _send_priority_menu(chat_id, order_id, telegram, admin_api)
        elif action == "validate":
            try:
                admin_api.revalidate_service_order(
                    order_id,
                    actor=_telegram_actor(chat_id),
                )
            except TelegramControlError as exc:
                logger.warning("Could not revalidate order from Telegram: %s", exc)
                telegram.send_message(chat_id, "No pude iniciar la validacion.")
            else:
                _record_audit_safe(
                    actor=_telegram_actor(chat_id),
                    action="order_revalidate",
                    status="accepted",
                    target_type="service_order",
                    target_id=order_id,
                )
                telegram.send_message(
                    chat_id,
                    "Validacion iniciada. Consulta el cliente en unos segundos.",
                    reply_markup={
                        "inline_keyboard": [[
                            {"text": "Ver cliente", "callback_data": f"om:{order_id}:show"},
                            {"text": "Menu", "callback_data": "ui:menu:main"},
                        ]]
                    },
                )
        elif action == "editrules":
            search_conversations.pop(chat_id, None)
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
    values = {
        "type_dni": "dni",
        "type_ce": "ce",
        "source_tiktok": "tiktok",
        "source_facebook": "facebook",
        "source_whatsapp": "whatsapp",
        "phone_omit": "OMITIR",
        "rules_none": "SIN_RESTRICCIONES",
        "rules_yes": "CON_RESTRICCIONES",
        "value_clear": "quitar",
        "days_mon_fri": "1,2,3,4,5",
        "days_mon_sat": "1,2,3,4,5,6",
        "days_sat": "6",
    }
    value = values.get(action)
    if value is None:
        telegram.send_message(chat_id, "Opcion de registro no reconocida.")
        return True
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
    if chat_id not in config.authorized_chat_ids:
        logger.warning("Ignored Telegram callback from an unauthorized chat.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="callback", status="denied"
        )
        return
    if not rate_limiter.allow(chat_id, mutation=True):
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="callback", status="rate_limited"
        )
        telegram.answer_callback_query(callback_id, "Espera un minuto y vuelve a intentar.")
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
    if parts[2] == "no":
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action=confirmation.command,
            status="cancelled", operation_id=operation_id,
        )
        telegram.answer_callback_query(callback_id, "Operacion cancelada.")
        telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
        return
    telegram.answer_callback_query(callback_id, "Solicitud confirmada.")
    _record_audit_safe(
        actor=_telegram_actor(chat_id), action=confirmation.command,
        status="accepted", operation_id=operation_id,
    )
    executor.submit(
        _execute_worker_command,
        confirmation,
        telegram,
        admin_api,
    )


def _execute_order_change(
    change: PendingOrderChange,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    operation_short = change.operation_id[:8]
    actor = _telegram_actor(change.chat_id)
    try:
        if change.action == "priority":
            admin_api.update_order_priority(
                change.order_id,
                int(change.updated["priority"]),
                actor=actor,
            )
        else:
            admin_api.update_order_rules(change.order_id, change.updated, actor=actor)
        verified = admin_api.get_service_order(change.order_id)
        if not _order_change_matches(change, verified):
            raise TelegramControlError("Saved order values do not match the requested change.")
        validation_text = ""
        if change.action == "rules" and str(verified.get("preflight_status") or "") != "validated":
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
        telegram.send_message(
            change.chat_id,
            "Cambio aplicado y verificado.\n"
            f"Solicitud: {operation_short}\n"
            f"Orden: {change.order_id}"
            f"{validation_text}",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "Ver cliente", "callback_data": f"om:{change.order_id}:show"}],
                    [
                        {"text": "Ver cliente", "callback_data": f"om:{change.order_id}:show"},
                        {"text": "Menu", "callback_data": "ui:menu:main"},
                    ],
                ]
            },
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
    try:
        created = admin_api.create_service_order(creation.values, actor=actor)
        order_id = str(created.get("order_id") or "")
        if not order_id:
            raise TelegramControlError("Admin API did not return an order_id.")
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
                "muestro los valores enviados."
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
        logger.info("Created service order from Telegram actor=%s order_id=%s", actor, order_id)
        _record_audit_safe(
            actor=actor,
            action="client_create",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            operation_id=creation.operation_id,
            detail=f"preflight_status={preflight}",
        )
    except TelegramControlError as exc:
        logger.warning("Telegram manual client creation failed: %s", exc)
        telegram.send_message(
            creation.chat_id,
            "No pude confirmar el alta. Consulta Clientes antes de volver a intentarlo.",
        )
        _record_audit_safe(
            actor=actor,
            action="client_create",
            status="failed",
            operation_id=creation.operation_id,
            detail="Admin API manual client creation could not be confirmed.",
        )
    except Exception:
        logger.exception("Unexpected Telegram manual client creation failure")


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
    return all(order.get(field) == value for field, value in change.updated.items())


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


def _telegram_actor(chat_id: str) -> str:
    digest = hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:12]
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


def _send_startup_notice(
    config: TelegramControlConfig,
    telegram: TelegramBotApi,
    worker: dict[str, Any],
) -> None:
    phase = str(worker.get("phase") or "desconocida")
    message = (
        "CONTROL REMOTO DISPONIBLE\n\n"
        "El receptor de Telegram acaba de iniciar o recuperarse.\n"
        f"Worker: {'activo' if worker.get('worker_running') else 'sin confirmar'}\n"
        f"Fase: {phase}\n\n"
        "Usa /estado para actualizar la informacion."
    )
    for chat_id in config.authorized_chat_ids:
        try:
            telegram.send_message(chat_id, message, reply_markup=_main_menu_markup())
        except TelegramControlError:
            logger.warning("Could not deliver Telegram control startup notice.")


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
