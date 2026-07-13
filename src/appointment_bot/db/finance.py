from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _settings, init_database


def list_finance_categories(*, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT category_code, display_name, cost_behavior, active
            FROM finance_categories
            ORDER BY display_name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_finance_entries(
    month_start: date,
    next_month_start: date,
    *,
    include_voided: bool = True,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = _settings(settings)
    init_database(settings)
    status_sql = "" if include_voided else "AND fe.status = 'active'"
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            f"""
            SELECT fe.*, fc.display_name AS category_name, fc.cost_behavior
            FROM finance_entries fe
            JOIN finance_categories fc USING (category_code)
            WHERE fe.occurred_on >= %s AND fe.occurred_on < %s
              {status_sql}
            ORDER BY fe.occurred_on DESC, fe.created_at DESC
            """,
            (month_start, next_month_start),
        ).fetchall()
    return [_finance_entry(row) for row in rows]


def create_finance_entry(
    values: dict[str, Any], *, settings: Settings | None = None
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    now = datetime.now(UTC)
    entry_id = f"finance-{uuid4()}"
    with _connection(_database_url(settings)) as connection:
        _validate_finance_references(connection, values)
        row = connection.execute(
            """
            INSERT INTO finance_entries (
                entry_id, occurred_on, entry_kind, category_code, vendor, description,
                amount_original, currency, exchange_rate_pen, amount_pen, quantity, unit,
                channel, campaign, order_id, evidence_reference, notes, data_quality,
                status, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, 'active', %s, %s
            )
            RETURNING *
            """,
            (
                entry_id,
                values["occurred_on"],
                values["entry_kind"],
                values["category_code"],
                values.get("vendor"),
                values["description"],
                values["amount_original"],
                values["currency"],
                values.get("exchange_rate_pen"),
                values.get("amount_pen"),
                values.get("quantity"),
                values.get("unit"),
                values.get("channel"),
                values.get("campaign"),
                values.get("order_id"),
                values.get("evidence_reference"),
                values.get("notes"),
                values["data_quality"],
                now,
                now,
            ),
        ).fetchone()
    return _finance_entry(row)


def update_finance_entry(
    entry_id: str,
    values: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        _validate_finance_references(connection, values)
        row = connection.execute(
            """
            UPDATE finance_entries
            SET occurred_on = %s, entry_kind = %s, category_code = %s, vendor = %s,
                description = %s, amount_original = %s, currency = %s,
                exchange_rate_pen = %s, amount_pen = %s, quantity = %s, unit = %s,
                channel = %s, campaign = %s, order_id = %s, evidence_reference = %s,
                notes = %s, data_quality = %s, updated_at = %s
            WHERE entry_id = %s AND status = 'active'
            RETURNING *
            """,
            (
                values["occurred_on"],
                values["entry_kind"],
                values["category_code"],
                values.get("vendor"),
                values["description"],
                values["amount_original"],
                values["currency"],
                values.get("exchange_rate_pen"),
                values.get("amount_pen"),
                values.get("quantity"),
                values.get("unit"),
                values.get("channel"),
                values.get("campaign"),
                values.get("order_id"),
                values.get("evidence_reference"),
                values.get("notes"),
                values["data_quality"],
                datetime.now(UTC),
                entry_id,
            ),
        ).fetchone()
    if row is None:
        raise ValueError("Finance entry not found or already voided.")
    return _finance_entry(row)


def void_finance_entry(
    entry_id: str,
    reason: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    now = datetime.now(UTC)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE finance_entries
            SET status = 'voided', voided_at = %s, void_reason = %s, updated_at = %s
            WHERE entry_id = %s AND status = 'active'
            RETURNING *
            """,
            (now, reason, now, entry_id),
        ).fetchone()
    if row is None:
        raise ValueError("Finance entry not found or already voided.")
    return _finance_entry(row)


def finance_month_summary(
    month_start: date,
    next_month_start: date,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        totals = connection.execute(
            """
            SELECT
                COALESCE(SUM(amount_pen) FILTER (
                    WHERE entry_kind IN ('expense', 'prepaid_consumption')
                ), 0) - COALESCE(SUM(amount_pen) FILTER (WHERE entry_kind = 'refund'), 0)
                    AS recognized_costs,
                COALESCE(SUM(amount_pen) FILTER (
                    WHERE entry_kind IN ('expense', 'prepaid_topup')
                ), 0) - COALESCE(SUM(amount_pen) FILTER (WHERE entry_kind = 'refund'), 0)
                    AS net_cash_outflow,
                COALESCE(SUM(amount_pen) FILTER (WHERE entry_kind = 'prepaid_topup'), 0)
                    AS prepaid_topups,
                COALESCE(SUM(amount_pen) FILTER (WHERE entry_kind = 'prepaid_consumption'), 0)
                    AS prepaid_consumption,
                COUNT(*) FILTER (WHERE amount_pen IS NULL) AS unconverted_entries,
                COUNT(*) AS active_entries
            FROM finance_entries
            WHERE status = 'active' AND occurred_on >= %s AND occurred_on < %s
            """,
            (month_start, next_month_start),
        ).fetchone()
        revenue = connection.execute(
            """
            SELECT COALESCE(SUM(amount_paid), 0) AS amount
            FROM payments
            WHERE status = 'paid' AND paid_at IS NOT NULL
              AND (paid_at AT TIME ZONE 'America/Lima')::date >= %s
              AND (paid_at AT TIME ZONE 'America/Lima')::date < %s
            """,
            (month_start, next_month_start),
        ).fetchone()
        categories = connection.execute(
            """
            SELECT fe.category_code, fc.display_name,
                   COALESCE(SUM(fe.amount_pen) FILTER (
                       WHERE fe.entry_kind IN ('expense', 'prepaid_consumption')
                   ), 0) - COALESCE(SUM(fe.amount_pen) FILTER (
                       WHERE fe.entry_kind = 'refund'
                   ), 0) AS recognized_cost
            FROM finance_entries fe
            JOIN finance_categories fc USING (category_code)
            WHERE fe.status = 'active' AND fe.occurred_on >= %s AND fe.occurred_on < %s
            GROUP BY fe.category_code, fc.display_name
            ORDER BY recognized_cost DESC, fc.display_name
            """,
            (month_start, next_month_start),
        ).fetchall()
    income = _money(revenue["amount"])
    costs = _money(totals["recognized_costs"])
    return {
        "month": month_start.strftime("%Y-%m"),
        "revenue_collected": income,
        "recognized_costs": costs,
        "operating_margin_before_unregistered_costs": round(income - costs, 2),
        "net_cash_outflow": _money(totals["net_cash_outflow"]),
        "prepaid_topups": _money(totals["prepaid_topups"]),
        "prepaid_consumption": _money(totals["prepaid_consumption"]),
        "unconverted_entries": int(totals["unconverted_entries"] or 0),
        "active_entries": int(totals["active_entries"] or 0),
        "is_complete": int(totals["unconverted_entries"] or 0) == 0,
        "by_category": [
            {
                "category_code": str(row["category_code"]),
                "category_name": str(row["display_name"]),
                "recognized_cost": _money(row["recognized_cost"]),
            }
            for row in categories
        ],
    }


def _finance_entry(row: Any) -> dict[str, Any]:
    payload = dict(row)
    for key in ("amount_original", "exchange_rate_pen", "amount_pen", "quantity"):
        payload[key] = float(payload[key]) if payload.get(key) is not None else None
    for key in ("occurred_on", "created_at", "updated_at", "voided_at"):
        value = payload.get(key)
        payload[key] = value.isoformat() if value is not None else None
    return payload


def _validate_finance_references(connection: Any, values: dict[str, Any]) -> None:
    category = connection.execute(
        "SELECT 1 FROM finance_categories WHERE category_code = %s AND active = true",
        (values["category_code"],),
    ).fetchone()
    if category is None:
        raise ValueError("Finance category not found or inactive.")
    order_id = values.get("order_id")
    if order_id is None:
        return
    order = connection.execute(
        "SELECT 1 FROM service_orders WHERE order_id = %s",
        (order_id,),
    ).fetchone()
    if order is None:
        raise ValueError("Related service order not found.")


def _money(value: Any) -> float:
    return float(Decimal(value or 0).quantize(Decimal("0.01")))
