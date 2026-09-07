from __future__ import annotations

import json
import logging
import secrets
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.transport import (
    _read_json_response,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


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
