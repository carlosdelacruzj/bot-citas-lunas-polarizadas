from __future__ import annotations

import argparse
import json
import logging
import os
import signal
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings, load_settings
from appointment_bot.services.logger import setup_logging

logger = logging.getLogger(__name__)

LIMA_TIMEZONE = ZoneInfo("America/Lima")
DEFAULT_ADMIN_API_URL = "http://127.0.0.1:8766"
DEFAULT_POLL_TIMEOUT_SECONDS = 30
RETRY_DELAY_SECONDS = 5
MAX_TELEGRAM_RESPONSE_BYTES = 1024 * 1024
HELP_TEXT = """Control remoto disponible:

/estado - Estado real del worker
/ayuda - Mostrar esta ayuda
/cancelar - Cancelar la operacion guiada actual

Los comandos que cambian estado se habilitaran en la siguiente fase."""


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


class AdminApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get_worker(self) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}/api/v1/worker",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return _read_json_response(response)
        except HTTPError as exc:
            raise TelegramControlError(
                f"Admin API rejected worker status with HTTP {exc.code}."
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
            "allowed_updates": json.dumps(["message"]),
        }
        if offset is not None:
            payload["offset"] = str(offset)
        data = self._request("getUpdates", payload, request_timeout=timeout_seconds + 10)
        result = data.get("result", [])
        if not isinstance(result, list):
            raise TelegramControlError("Telegram returned an invalid updates list.")
        return [item for item in result if isinstance(item, dict)]

    def send_message(self, chat_id: str, text: str) -> None:
        self._request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            },
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
    logger.info("Telegram control long polling started.")
    while not stop_event.is_set():
        try:
            updates = telegram.get_updates(
                offset=next_offset,
                timeout_seconds=config.poll_timeout_seconds,
            )
            for update in updates:
                update_id = _update_id(update)
                if update_id is None:
                    continue
                _process_update(update, config, telegram, admin_api)
                next_offset = update_id + 1
                _store_next_offset(config.offset_path, next_offset)
        except TelegramControlError as exc:
            logger.warning("Telegram control polling failed: %s", exc)
            stop_event.wait(RETRY_DELAY_SECONDS)
        except Exception:
            logger.exception("Unexpected Telegram control polling failure")
            stop_event.wait(RETRY_DELAY_SECONDS)
    logger.info("Telegram control stopped.")
    return 0


def _process_update(
    update: dict[str, Any],
    config: TelegramControlConfig,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
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
    command = _command_name(text)
    if command is None:
        return
    if command in {"ayuda", "help", "start"}:
        telegram.send_message(chat_id, HELP_TEXT)
        return
    if command == "cancelar":
        telegram.send_message(chat_id, "No hay una operacion guiada activa.")
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
    telegram.send_message(chat_id, "Comando no reconocido. Usa /ayuda.")


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


def _command_name(text: str) -> str | None:
    first = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    if not first.startswith("/"):
        return None
    return first[1:].split("@", maxsplit=1)[0].strip().lower() or None


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
