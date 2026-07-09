from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from appointment_bot.services.api.http import error_payload
from appointment_bot.services.postgres_orders import (
    add_or_update_service_order_contact,
    create_service_order,
    list_service_order_summaries,
    mark_order_done,
    mark_payment_paid,
    mark_service_order_no_charge,
    set_order_paused,
)

PUBLIC_SERVICE_ORDER_FIELDS = (
    "order_id",
    "applicant_id",
    "applicant_name",
    "document_number_masked",
    "contact_name",
    "contact_whatsapp_masked",
    "contact_source",
    "priority",
    "charge_required",
    "status",
    "reservation_status",
    "reservation_site",
    "reservation_date",
    "reservation_hour",
    "payment_status",
    "amount_agreed",
    "amount_paid",
    "parent_order_id",
    "program_expediente",
    "program_plate",
    "minimum_reservation_hour",
    "minimum_reservation_date",
    "allowed_weekdays",
    "created_at",
    "updated_at",
)


def list_service_orders_payload() -> dict[str, Any]:
    return {
        "service_orders": [
            _public_service_order(order) for order in list_service_order_summaries()
        ]
    }


def create_service_order_payload(payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    required = ("document_number", "password")
    missing = [field for field in required if payload.get(field) in {None, ""}]
    if missing:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            f"Missing fields: {', '.join(missing)}",
        )
    try:
        result = create_service_order(
            document_number=str(payload["document_number"]).strip(),
            password=str(payload["password"]),
            priority=int(payload.get("priority", 0) or 0),
            contact_whatsapp=_optional_text(payload, "contact_whatsapp"),
            contact_name=_optional_text(payload, "contact_name"),
            contact_source=_optional_text(payload, "contact_source"),
            applicant_name=_optional_text(payload, "applicant_name"),
            charge_required=_optional_bool(payload, "charge_required", default=True),
            minimum_reservation_hour=(
                int(payload["minimum_reservation_hour"])
                if payload.get("minimum_reservation_hour") not in {None, ""}
                else None
            ),
            minimum_reservation_date=_optional_text(payload, "minimum_reservation_date"),
            allowed_weekdays=_optional_weekdays(payload.get("allowed_weekdays")),
            parent_order_id=_optional_text(payload, "parent_order_id"),
            program_expediente=_optional_text(payload, "program_expediente"),
            program_plate=_optional_text(payload, "program_plate"),
        )
    except (TypeError, ValueError) as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.CREATED, {"status": "created", **asdict(result)}


def update_service_order_contact_payload(
    order_id: str,
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    if payload.get("contact_whatsapp") in {None, ""} and payload.get("contact_name") in {
        None,
        "",
    }:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            "Missing contact_whatsapp or contact_name.",
        )
    try:
        add_or_update_service_order_contact(
            order_id,
            contact_whatsapp=_optional_text(payload, "contact_whatsapp"),
            contact_name=_optional_text(payload, "contact_name"),
            contact_source=_optional_text(payload, "contact_source"),
        )
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))
    return HTTPStatus.OK, {"status": "ok"}


def apply_service_order_action(path: str) -> tuple[HTTPStatus, dict[str, Any]] | None:
    action = service_order_action(path)
    if action is None:
        return None
    order_id, action_name = action
    try:
        if action_name == "pause":
            set_order_paused(order_id, True)
        elif action_name == "activate":
            set_order_paused(order_id, False)
        elif action_name == "done":
            mark_order_done(order_id, status="completed")
        elif action_name == "no-charge":
            mark_service_order_no_charge(order_id)
        else:
            raise ValueError(f"Unsupported service order action: {action_name}")
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))
    return HTTPStatus.OK, {"status": "ok"}


def mark_payment_paid_payload(
    order_id: str,
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    if payload.get("amount_paid") in {None, ""}:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", "Missing amount_paid.")
    try:
        mark_payment_paid(
            order_id,
            amount_paid=payload["amount_paid"],
            amount_agreed=payload.get("amount_agreed"),
        )
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.OK, {"status": "ok"}


def service_order_contact_path(path: str) -> str | None:
    prefix = "/api/v1/service-orders/"
    suffix = "/contact"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    return unquote(path.removeprefix(prefix).removesuffix(suffix).strip("/"))


def service_order_action(path: str) -> tuple[str, str] | None:
    prefix = "/api/v1/service-orders/"
    if not path.startswith(prefix):
        return None
    parts = [unquote(part) for part in path.removeprefix(prefix).split("/") if part]
    if len(parts) != 2:
        return None
    order_id, action = parts
    if action not in {"pause", "activate", "done", "no-charge"}:
        return None
    return order_id, action


def payment_paid_path(path: str) -> str | None:
    prefix = "/api/v1/service-orders/"
    suffix = "/payment/paid"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    return unquote(path.removeprefix(prefix).removesuffix(suffix).strip("/"))


def _optional_text(payload: dict[str, Any], name: str) -> str | None:
    if name not in payload or payload[name] in {None, ""}:
        return None
    return str(payload[name]).strip()


def _optional_weekdays(value: Any) -> list[int] | None:
    if value in {None, ""}:
        return None
    if isinstance(value, list):
        return [int(item) for item in value]
    return [int(item.strip()) for item in str(value).split(",") if item.strip()]


def _optional_bool(payload: dict[str, Any], name: str, *, default: bool) -> bool:
    value = payload.get(name, default)
    if isinstance(value, bool):
        return value
    if value in {None, ""}:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {value!r}")


def _public_service_order(order: Any) -> dict[str, Any]:
    payload = asdict(order)
    return {field: payload.get(field) for field in PUBLIC_SERVICE_ORDER_FIELDS}
