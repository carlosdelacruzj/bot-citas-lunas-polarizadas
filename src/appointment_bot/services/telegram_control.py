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
from appointment_bot.services.logger import setup_logging
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)

LIMA_TIMEZONE = ZoneInfo("America/Lima")
DEFAULT_ADMIN_API_URL = "http://127.0.0.1:8766"
DEFAULT_POLL_TIMEOUT_SECONDS = 30
RETRY_DELAY_SECONDS = 5
CONFIRMATION_TTL_SECONDS = 120
CONVERSATION_TTL_SECONDS = 300
WORKER_COMMAND_TIMEOUT_SECONDS = 90
MAX_TELEGRAM_RESPONSE_BYTES = 1024 * 1024
CLIENTS_PAGE_SIZE = 8
HELP_TEXT = """Control remoto disponible:

/estado - Estado real del worker
/clientes [pagina] - Resumen paginado de la cola
/cliente ORDER_ID - Detalle operativo enmascarado
/reglas ORDER_ID - Restricciones de una orden
/ultimos_errores - Incidentes operativos recientes
/prioridad ORDER_ID VALOR - Cambiar prioridad con confirmacion
/reglas_editar ORDER_ID - Editar restricciones paso a paso
/pausar - Pausar el worker con confirmacion
/reanudar - Reanudar el worker con confirmacion
/reiniciar - Reiniciar el worker con confirmacion
/ayuda - Mostrar esta ayuda
/cancelar - Cancelar la operacion guiada actual
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
    ) -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        self._request(
            "sendMessage",
            payload,
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
    confirmation_lock = Lock()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="telegram-worker-command")
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
                        confirmation_lock=confirmation_lock,
                        executor=executor,
                    )
                    next_offset = update_id + 1
                    _store_next_offset(config.offset_path, next_offset)
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
        return
    text = message.get("text")
    if not isinstance(text, str):
        return
    if not text.strip().startswith("/"):
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
    if command in {"ayuda", "help", "start"}:
        telegram.send_message(chat_id, HELP_TEXT)
        return
    if command == "cancelar":
        removed = _cancel_chat_confirmations(chat_id, pending_confirmations, confirmation_lock)
        order_removed = _cancel_chat_order_state(
            chat_id,
            pending_order_changes,
            rules_conversations,
            confirmation_lock,
        )
        response = (
            "Operacion pendiente cancelada."
            if removed or order_removed
            else "No hay una operacion guiada activa."
        )
        telegram.send_message(chat_id, response)
        return
    if command == "estado":
        try:
            payload = admin_api.get_worker()
            response = format_worker_status(payload)
        except TelegramControlError as exc:
            logger.warning("Could not read worker status: %s", exc)
            response = "No pude consultar el estado del sistema. La Admin API no responde."
        telegram.send_message(chat_id, response)
        return
    if command == "clientes":
        _send_clients(chat_id, arguments, telegram, admin_api)
        return
    if command in {"cliente", "reglas"}:
        _send_order_query(chat_id, command, arguments, telegram, admin_api)
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
            f"Estado: {order.get('status') or 'desconocido'} | "
            f"Prioridad: {order.get('priority', 0)}"
        )
    if not visible:
        lines.append("No hay clientes registrados.")
    if page < total_pages:
        lines.extend(["", f"Siguiente: /clientes {page + 1}"])
    telegram.send_message(chat_id, "\n\n".join(lines))


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
    telegram.send_message(chat_id, response)


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
    telegram.send_message(chat_id, "\n\n".join(lines))


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
        f"WhatsApp: {order.get('contact_whatsapp') or 'no registrado'}",
        f"Fuente: {order.get('contact_source') or 'no registrada'}",
        "",
        f"Estado: {order.get('status') or 'desconocido'}",
        f"Preflight: {order.get('preflight_status') or 'desconocido'}",
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
            f"Hora minima: {_format_minimum_hour(order.get('minimum_reservation_hour'))}",
            f"Dias permitidos: {weekday_text}",
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


def _format_minimum_hour(value: Any) -> str:
    if value in {None, ""}:
        return "sin limite"
    try:
        return f"{int(value):02d}:00"
    except (TypeError, ValueError):
        return "desconocida"


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
    try:
        field, value = _parse_rules_step(conversation.step, text, conversation.updated)
    except ValueError as exc:
        telegram.send_message(chat_id, f"{exc}\n\n{_rules_step_prompt(conversation.step)}")
        return True
    conversation.updated[field] = value
    conversation.step += 1
    conversation.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
    if conversation.step < 4:
        telegram.send_message(chat_id, _rules_step_prompt(conversation.step))
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
        "minimum_reservation_hour",
        "allowed_weekdays",
    )
    field = fields[step]
    if value in {"igual", "mantener"}:
        return field, current.get(field)
    if value in {"quitar", "ninguno", "todos"}:
        return field, None
    if step in {0, 1}:
        try:
            parsed = datetime.strptime(value, "%d-%m-%Y").date()
        except ValueError as exc:
            raise ValueError("Usa DD-MM-YYYY, igual o quitar.") from exc
        return field, parsed.isoformat()
    if step == 2:
        try:
            hour = int(value)
        except ValueError as exc:
            raise ValueError("Usa una hora de 0 a 23, igual o quitar.") from exc
        if hour < 0 or hour > 23:
            raise ValueError("La hora debe estar entre 0 y 23.")
        return field, hour
    try:
        weekdays = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    except ValueError as exc:
        raise ValueError("Usa dias ISO separados por coma, igual o todos.") from exc
    if not weekdays or any(day < 1 or day > 7 for day in weekdays):
        raise ValueError("Los dias deben estar entre 1=lunes y 7=domingo.")
    return field, weekdays


def _rules_step_prompt(step: int) -> str:
    return (
        "Paso 1/4 - Fecha minima. Responde DD-MM-YYYY, igual o quitar.",
        "Paso 2/4 - Fecha maxima. Responde DD-MM-YYYY, igual o quitar.",
        "Paso 3/4 - Hora minima. Responde 0 a 23, igual o quitar.",
        "Paso 4/4 - Dias permitidos. Responde 1,2,...7; igual o todos.",
    )[step]


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
        "minimum_reservation_hour": order.get("minimum_reservation_hour"),
        "allowed_weekdays": list(weekdays) if isinstance(weekdays, list) else None,
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
            "Hora minima: "
            + _change_value(change.original, change.updated, "minimum_reservation_hour"),
            f"Dias: {_change_value(change.original, change.updated, 'allowed_weekdays')}",
        ]
    )


def _change_value(original: dict[str, Any], updated: dict[str, Any], field: str) -> str:
    old = original.get(field)
    new = updated.get(field)
    if field in {"minimum_reservation_date", "maximum_reservation_date"}:
        return f"{_format_operator_date(old)} -> {_format_operator_date(new)}"
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


def _process_callback_query(
    callback_query: dict[str, Any],
    config: TelegramControlConfig,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    pending_order_changes: dict[str, PendingOrderChange],
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
        return
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in {"wc", "oc"} or parts[2] not in {"yes", "no"}:
        telegram.answer_callback_query(callback_id, "Accion no reconocida.")
        return
    operation_id = parts[1]
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
            telegram.answer_callback_query(callback_id, "Operacion cancelada.")
            telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
            return
        telegram.answer_callback_query(callback_id, "Cambio confirmado.")
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
        telegram.answer_callback_query(callback_id, "Operacion cancelada.")
        telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
        return
    telegram.answer_callback_query(callback_id, "Solicitud confirmada.")
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
        telegram.send_message(
            change.chat_id,
            "Cambio aplicado y verificado.\n"
            f"Solicitud: {operation_short}\n"
            f"Orden: {change.order_id}",
        )
        logger.info(
            "Applied Telegram order change action=%s actor=%s order_id=%s",
            change.action,
            actor,
            change.order_id,
        )
    except TelegramControlError as exc:
        logger.warning("Order change %s failed: %s", change.action, exc)
        telegram.send_message(
            change.chat_id,
            f"No pude verificar la solicitud {operation_short}. No confirmo el cambio.",
        )
    except Exception:
        logger.exception("Unexpected order change execution failure")


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
            return
        worker = _wait_for_worker_effect(admin_api, confirmation.command)
        telegram.send_message(
            confirmation.chat_id,
            _format_worker_command_success(confirmation.command, operation_short, worker),
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
