from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

from appointment_bot.db.finance import (
    create_finance_entry,
    finance_data_quality,
    finance_month_closure,
    finance_month_summary,
    list_finance_categories,
    list_finance_entries,
    reconcile_payment_amount,
    update_finance_entry,
    upsert_finance_month_closure,
    void_finance_entry,
)
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.api.monthly_dashboard_routes import LIMA_TZ, _shift_month

ENTRY_KINDS = {"expense", "prepaid_topup", "prepaid_consumption", "refund"}
DATA_QUALITIES = {"actual", "estimated", "pending"}
PAYMENT_RESOLUTION_TYPES = {"discount", "waiver", "correction"}


def finance_categories_payload() -> dict[str, Any]:
    return {"categories": list_finance_categories()}


def finance_entries_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    parsed = _month_range(query)
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[0], HTTPStatus):
        return parsed
    month_start, next_month_start = parsed
    include_voided = query.get("include_voided", ["1"])[0].strip() != "0"
    return HTTPStatus.OK, {
        "month": month_start.strftime("%Y-%m"),
        "entries": list_finance_entries(
            month_start,
            next_month_start,
            include_voided=include_voided,
        ),
    }


def finance_summary_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    parsed = _month_range(query)
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[0], HTTPStatus):
        return parsed
    month_start, next_month_start = parsed
    return HTTPStatus.OK, finance_month_summary(month_start, next_month_start)


def finance_data_quality_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    parsed = _month_range(query)
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[0], HTTPStatus):
        return parsed
    month_start, next_month_start = parsed
    return HTTPStatus.OK, finance_data_quality(month_start, next_month_start)


def finance_month_closure_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    parsed = _month_range(query)
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[0], HTTPStatus):
        return parsed
    month_start, next_month_start = parsed
    return HTTPStatus.OK, finance_month_closure(month_start, next_month_start)


def upsert_finance_month_closure_payload(
    payload: dict[str, Any],
    *,
    requested_by: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    parsed = _month_range({"month": [str(payload.get("month") or "").strip()]})
    if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[0], HTTPStatus):
        return parsed
    month_start, next_month_start = parsed
    try:
        values = _normalize_month_closure(payload, requested_by=requested_by)
        closure = upsert_finance_month_closure(
            month_start, next_month_start, values
        )
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.OK, {"status": "saved", **closure}


def reconcile_payment_amount_payload(
    payment_id: str,
    payload: dict[str, Any],
    *,
    requested_by: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    resolution_type = str(payload.get("resolution_type") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if resolution_type not in PAYMENT_RESOLUTION_TYPES:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "resolution_type must be discount, waiver or correction."
        )
    if len(reason) < 3:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "reason must contain at least 3 characters."
        )
    try:
        reconciliation = reconcile_payment_amount(
            payment_id,
            resolution_type=resolution_type,
            reason=reason,
            reconciled_by=requested_by,
        )
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))
    return HTTPStatus.OK, {"status": "reconciled", "reconciliation": reconciliation}


def create_finance_entry_payload(
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        values = _normalize_entry(payload)
        entry = create_finance_entry(values)
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    return HTTPStatus.CREATED, {"status": "created", "entry": entry}


def update_finance_entry_payload(
    entry_id: str,
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        values = _normalize_entry(payload)
        entry = update_finance_entry(entry_id, values)
    except ValueError as exc:
        status = HTTPStatus.NOT_FOUND if "not found" in str(exc).lower() else HTTPStatus.BAD_REQUEST
        return status, error_payload(
            "not_found" if status == HTTPStatus.NOT_FOUND else "bad_request",
            str(exc),
        )
    return HTTPStatus.OK, {"status": "updated", "entry": entry}


def void_finance_entry_payload(
    entry_id: str,
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 3:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "Void reason must contain at least 3 characters."
        )
    try:
        entry = void_finance_entry(entry_id, reason)
    except ValueError as exc:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", str(exc))
    return HTTPStatus.OK, {"status": "voided", "entry": entry}


def finance_entry_action_path(path: str, action: str) -> str | None:
    prefix = "/api/v1/finance/entries/"
    suffix = f"/{action}"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    entry_id = unquote(path[len(prefix) : -len(suffix)]).strip()
    return entry_id or None


def finance_payment_reconciliation_path(path: str) -> str | None:
    prefix = "/api/v1/finance/payments/"
    suffix = "/reconcile-amount"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    payment_id = unquote(path[len(prefix) : -len(suffix)]).strip()
    return payment_id or None


def _month_range(
    query: dict[str, list[str]],
) -> tuple[date, date] | tuple[HTTPStatus, dict[str, Any]]:
    raw_month = query.get("month", [datetime.now(LIMA_TZ).strftime("%Y-%m")])[0].strip()
    try:
        month_start = datetime.strptime(raw_month, "%Y-%m").date().replace(day=1)
    except ValueError:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", "month must use YYYY-MM.")
    return month_start, _shift_month(month_start, 1)


def _normalize_entry(payload: dict[str, Any]) -> dict[str, Any]:
    required = ("occurred_on", "entry_kind", "category_code", "description", "amount_original")
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}")
    try:
        occurred_on = datetime.strptime(str(payload["occurred_on"]), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("occurred_on must use YYYY-MM-DD.") from exc
    entry_kind = str(payload["entry_kind"]).strip()
    if entry_kind not in ENTRY_KINDS:
        raise ValueError("Unsupported entry_kind.")
    data_quality = str(payload.get("data_quality") or "actual").strip()
    if data_quality not in DATA_QUALITIES:
        raise ValueError("Unsupported data_quality.")
    amount_original = _positive_decimal(payload["amount_original"], "amount_original", "0.0001")
    currency = str(payload.get("currency") or "PEN").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must use a three-letter ISO code.")
    exchange_rate = _optional_positive_decimal(
        payload.get("exchange_rate_pen"), "exchange_rate_pen"
    )
    if currency == "PEN":
        exchange_rate = Decimal("1")
        amount_pen = amount_original.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif exchange_rate is not None:
        amount_pen = (amount_original * exchange_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        amount_pen = None
        data_quality = "pending" if data_quality == "actual" else data_quality
    quantity = _optional_positive_decimal(payload.get("quantity"), "quantity")
    return {
        "occurred_on": occurred_on,
        "entry_kind": entry_kind,
        "category_code": str(payload["category_code"]).strip(),
        "vendor": _optional_text(payload.get("vendor")),
        "description": str(payload["description"]).strip(),
        "amount_original": amount_original,
        "currency": currency,
        "exchange_rate_pen": exchange_rate,
        "amount_pen": amount_pen,
        "quantity": quantity,
        "unit": _optional_text(payload.get("unit")),
        "channel": _optional_text(payload.get("channel")),
        "campaign": _optional_text(payload.get("campaign")),
        "order_id": _optional_text(payload.get("order_id")),
        "evidence_reference": _optional_text(payload.get("evidence_reference")),
        "notes": _optional_text(payload.get("notes")),
        "data_quality": data_quality,
    }


def _normalize_month_closure(
    payload: dict[str, Any],
    *,
    requested_by: str,
) -> dict[str, Any]:
    status = str(payload.get("status") or "draft").strip()
    if status not in {"draft", "reconciled"}:
        raise ValueError("status must be draft or reconciled.")
    opening = _optional_non_negative_decimal(
        payload.get("opening_prepaid_balance"), "opening_prepaid_balance"
    )
    closing = _optional_non_negative_decimal(
        payload.get("closing_prepaid_balance"), "closing_prepaid_balance"
    )
    if status == "reconciled" and (opening is None or closing is None):
        raise ValueError(
            "A reconciled close requires opening and closing balances."
        )
    return {
        "opening_prepaid_balance": opening,
        "closing_prepaid_balance": closing,
        "status": status,
        "reconciled_by": requested_by if status == "reconciled" else None,
        "notes": _optional_text(payload.get("notes")),
    }


def _positive_decimal(value: Any, field: str, quantum: str = "0.000001") -> Decimal:
    try:
        parsed = Decimal(str(value)).quantize(Decimal(quantum))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid number.") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be greater than zero.")
    return parsed


def _optional_positive_decimal(value: Any, field: str) -> Decimal | None:
    if value in {None, ""}:
        return None
    return _positive_decimal(value, field)


def _optional_non_negative_decimal(value: Any, field: str) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        parsed = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid number.") from exc
    if parsed < 0:
        raise ValueError(f"{field} must be zero or greater.")
    return parsed


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
