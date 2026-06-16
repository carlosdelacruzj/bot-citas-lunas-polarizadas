from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from appointment_bot.services.api.http import error_payload
from appointment_bot.services.database import (
    add_client,
    list_client_summaries,
    mark_client_done,
    set_client_active,
    update_client,
)


def list_clients_payload() -> dict[str, Any]:
    return {"clients": [asdict(client) for client in list_client_summaries()]}


def create_client(payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    required = ("client_id", "name", "username", "password", "priority")
    missing = [field for field in required if payload.get(field) in {None, ""}]
    if missing:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            f"Missing fields: {', '.join(missing)}",
        )
    try:
        add_client(
            str(payload["client_id"]).strip(),
            str(payload["name"]).strip(),
            str(payload["username"]).strip(),
            str(payload["password"]),
            int(payload["priority"]),
        )
    except (TypeError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.CREATED, {"status": "created"}


def update_client_payload(
    client_id: str, payload: dict[str, Any]
) -> tuple[HTTPStatus, dict[str, Any]]:
    allowed = {"name", "username", "password", "priority"}
    invalid = sorted(set(payload) - allowed)
    if invalid:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            f"Invalid fields: {', '.join(invalid)}",
        )
    try:
        update_client(
            client_id,
            name=_optional_text(payload, "name"),
            username=_optional_text(payload, "username"),
            password=_optional_text(payload, "password"),
            priority=int(payload["priority"]) if "priority" in payload else None,
        )
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))
    return HTTPStatus.OK, {"status": "ok"}


def apply_client_action(path: str) -> tuple[HTTPStatus, dict[str, Any]] | None:
    action = client_action(path)
    if action is None:
        return None
    client_id, action_name = action
    try:
        if action_name == "pause":
            set_client_active(client_id, False)
        elif action_name == "activate":
            set_client_active(client_id, True)
        elif action_name == "done":
            mark_client_done(client_id, status="completed")
        else:
            raise ValueError(f"Unsupported client action: {action_name}")
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))
    return HTTPStatus.OK, {"status": "ok"}


def client_action(path: str) -> tuple[str, str] | None:
    prefix = "/api/v1/clients/"
    if not path.startswith(prefix):
        return None
    parts = [unquote(part) for part in path.removeprefix(prefix).split("/") if part]
    if len(parts) != 2:
        return None
    client_id, action = parts
    if action not in {"pause", "activate", "done"}:
        return None
    return client_id, action


def client_id_from_path(path: str) -> str:
    return unquote(path.removeprefix("/api/v1/clients/")).strip()


def _optional_text(payload: dict[str, Any], name: str) -> str | None:
    if name not in payload:
        return None
    return str(payload[name])
