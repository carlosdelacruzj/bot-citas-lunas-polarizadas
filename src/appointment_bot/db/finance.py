from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _settings, init_database
from appointment_bot.db.payment_receipt_quality import payment_receipt_date_quality

LIMA_TZ = ZoneInfo("America/Lima")


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
            SELECT COALESCE(SUM(amount), 0) AS amount
            FROM payment_receipts
            WHERE (received_at AT TIME ZONE 'America/Lima')::date >= %s
              AND (received_at AT TIME ZONE 'America/Lima')::date < %s
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
        receipt_date_quality = payment_receipt_date_quality(
            connection,
            month_start,
            next_month_start,
        )
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
        "conversion_complete": int(totals["unconverted_entries"] or 0) == 0,
        "receipt_date_quality": receipt_date_quality,
        "cost_capture_complete": None,
        "completeness_semantics": (
            "conversion_complete only confirms that every active movement in the period has a PEN "
            "conversion; it does not attest that all costs were captured or that margin is "
            "net profit."
        ),
        "by_category": [
            {
                "category_code": str(row["category_code"]),
                "category_name": str(row["display_name"]),
                "recognized_cost": _money(row["recognized_cost"]),
            }
            for row in categories
        ],
    }


def finance_data_quality(
    month_start: date,
    next_month_start: date,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        quality_rows = connection.execute(
            """
            SELECT data_quality, COUNT(*) AS entry_count,
                   COALESCE(SUM(amount_pen), 0) AS amount_pen,
                   COUNT(*) FILTER (WHERE amount_pen IS NULL) AS unconverted_count
            FROM finance_entries
            WHERE status = 'active' AND occurred_on >= %s AND occurred_on < %s
            GROUP BY data_quality
            """,
            (month_start, next_month_start),
        ).fetchall()
        unconverted_rows = connection.execute(
            """
            SELECT entry_id, occurred_on, entry_kind, category_code, description,
                   amount_original, currency, data_quality
            FROM finance_entries
            WHERE status = 'active' AND occurred_on >= %s AND occurred_on < %s
              AND amount_pen IS NULL
            ORDER BY occurred_on, created_at
            """,
            (month_start, next_month_start),
        ).fetchall()
        mismatch_rows = connection.execute(
            """
            SELECT p.payment_id, p.order_id, p.amount_agreed, p.amount_paid,
                   p.currency, p.paid_at, par.resolution_type, par.reason,
                   par.reconciled_by, par.reconciled_at
            FROM payments p
            LEFT JOIN payment_amount_reconciliations par USING (payment_id)
            WHERE p.status = 'paid'
              AND (p.paid_at AT TIME ZONE 'America/Lima')::date >= %s
              AND (p.paid_at AT TIME ZONE 'America/Lima')::date < %s
              AND p.amount_paid IS DISTINCT FROM p.amount_agreed
            ORDER BY p.paid_at, p.payment_id
            """,
            (month_start, next_month_start),
        ).fetchall()
        receipt_date_quality = payment_receipt_date_quality(
            connection,
            month_start,
            next_month_start,
        )

    qualities = {
        quality: {"entry_count": 0, "amount_pen": 0.0, "unconverted_count": 0}
        for quality in ("actual", "estimated", "pending")
    }
    for row in quality_rows:
        qualities[str(row["data_quality"])] = {
            "entry_count": int(row["entry_count"] or 0),
            "amount_pen": _money(row["amount_pen"]),
            "unconverted_count": int(row["unconverted_count"] or 0),
        }
    mismatches = []
    for row in mismatch_rows:
        agreed = row["amount_agreed"]
        paid = row["amount_paid"]
        mismatches.append(
            {
                "payment_id": str(row["payment_id"]),
                "order_id": str(row["order_id"]),
                "amount_agreed": _money(agreed) if agreed is not None else None,
                "amount_paid": _money(paid) if paid is not None else None,
                "difference": _money(paid - agreed)
                if agreed is not None and paid is not None
                else None,
                "currency": str(row["currency"]),
                "paid_at": row["paid_at"].isoformat() if row["paid_at"] is not None else None,
                "reconciliation": (
                    {
                        "resolution_type": str(row["resolution_type"]),
                        "reason": str(row["reason"]),
                        "reconciled_by": str(row["reconciled_by"]),
                        "reconciled_at": row["reconciled_at"].isoformat(),
                    }
                    if row["resolution_type"] is not None
                    else None
                ),
            }
        )
    unconverted = []
    for row in unconverted_rows:
        unconverted.append(
            {
                "entry_id": str(row["entry_id"]),
                "occurred_on": row["occurred_on"].isoformat(),
                "entry_kind": str(row["entry_kind"]),
                "category_code": str(row["category_code"]),
                "description": str(row["description"]),
                "amount_original": float(row["amount_original"]),
                "currency": str(row["currency"]),
                "data_quality": str(row["data_quality"]),
            }
        )
    return {
        "month": month_start.strftime("%Y-%m"),
        "receipt_date_quality": receipt_date_quality,
        "data_quality": qualities,
        "unconverted_entries": unconverted,
        "paid_amount_mismatches": mismatches,
        "unreconciled_paid_amount_mismatch_count": sum(
            item["reconciliation"] is None for item in mismatches
        ),
    }


def reconcile_payment_amount(
    payment_id: str,
    *,
    resolution_type: str,
    reason: str,
    reconciled_by: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    now = datetime.now(UTC)
    with _connection(_database_url(settings)) as connection:
        payment = connection.execute(
            """
            SELECT payment_id
            FROM payments
            WHERE payment_id = %s AND status = 'paid'
              AND amount_paid IS DISTINCT FROM amount_agreed
            """,
            (payment_id,),
        ).fetchone()
        if payment is None:
            raise ValueError("Paid payment amount mismatch not found.")
        row = connection.execute(
            """
            INSERT INTO payment_amount_reconciliations (
                payment_id, resolution_type, reason, reconciled_by, reconciled_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (payment_id) DO UPDATE SET
                resolution_type = excluded.resolution_type,
                reason = excluded.reason,
                reconciled_by = excluded.reconciled_by,
                reconciled_at = excluded.reconciled_at,
                updated_at = excluded.updated_at
            RETURNING *
            """,
            (payment_id, resolution_type, reason, reconciled_by, now, now),
        ).fetchone()
    payload = dict(row)
    for key in ("reconciled_at", "updated_at"):
        payload[key] = payload[key].isoformat()
    return payload


def finance_month_closure(
    month_start: date,
    next_month_start: date,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            "SELECT * FROM finance_month_closures WHERE month_start = %s",
            (month_start,),
        ).fetchone()
        movements = _finance_month_movements(connection, month_start, next_month_start)
    return _finance_month_closure_payload(month_start, row, movements)


def upsert_finance_month_closure(
    month_start: date,
    next_month_start: date,
    values: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    now = datetime.now(UTC)
    with _connection(_database_url(settings)) as connection:
        movements = _finance_month_movements(connection, month_start, next_month_start)
        if values["status"] == "reconciled":
            if datetime.now(LIMA_TZ).date() < next_month_start:
                raise ValueError("The current or a future month cannot be reconciled.")
            if movements["pending_entries"] or movements["unconverted_entries"]:
                raise ValueError(
                    "The month cannot be reconciled while pending or unconverted movements exist."
                )
            unresolved = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM payments p
                LEFT JOIN payment_amount_reconciliations par USING (payment_id)
                WHERE p.status = 'paid'
                  AND (p.paid_at AT TIME ZONE 'America/Lima')::date >= %s
                  AND (p.paid_at AT TIME ZONE 'America/Lima')::date < %s
                  AND p.amount_paid IS DISTINCT FROM p.amount_agreed
                  AND par.payment_id IS NULL
                """,
                (month_start, next_month_start),
            ).fetchone()
            if int(unresolved["count"] or 0):
                raise ValueError(
                    "The month cannot be reconciled while paid amount mismatches remain unresolved."
                )
            expected_closing = (
                values["opening_prepaid_balance"]
                + Decimal(str(movements["prepaid_topups"]))
                - Decimal(str(movements["prepaid_consumption"]))
                + Decimal(str(movements["prepaid_refunds"]))
            ).quantize(Decimal("0.01"))
            if values["closing_prepaid_balance"] != expected_closing:
                raise ValueError(
                    "The closing prepaid balance does not reconcile with recorded movements."
                )
        reconciled_at = now if values["status"] == "reconciled" else None
        reconciled_by = values.get("reconciled_by") if reconciled_at else None
        row = connection.execute(
            """
            INSERT INTO finance_month_closures (
                month_start, opening_prepaid_balance, closing_prepaid_balance, status,
                reconciled_at, reconciled_by, notes, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (month_start) DO UPDATE SET
                opening_prepaid_balance = excluded.opening_prepaid_balance,
                closing_prepaid_balance = excluded.closing_prepaid_balance,
                status = excluded.status,
                reconciled_at = excluded.reconciled_at,
                reconciled_by = excluded.reconciled_by,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            RETURNING *
            """,
            (
                month_start,
                values.get("opening_prepaid_balance"),
                values.get("closing_prepaid_balance"),
                values["status"],
                reconciled_at,
                reconciled_by,
                values.get("notes"),
                now,
                now,
            ),
        ).fetchone()
    return _finance_month_closure_payload(month_start, row, movements)


def _finance_month_movements(
    connection: Any, month_start: date, next_month_start: date
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            COALESCE(SUM(amount_pen) FILTER (WHERE entry_kind = 'prepaid_topup'), 0)
                AS prepaid_topups,
            COALESCE(SUM(amount_pen) FILTER (WHERE entry_kind = 'prepaid_consumption'), 0)
                AS prepaid_consumption,
            COALESCE(SUM(amount_pen) FILTER (WHERE entry_kind = 'refund'), 0)
                AS refunds,
            COALESCE(SUM(amount_pen) FILTER (
                WHERE entry_kind = 'refund' AND category_code = 'captcha'
            ), 0) AS prepaid_refunds,
            COUNT(*) FILTER (WHERE data_quality = 'pending') AS pending_entries,
            COUNT(*) FILTER (WHERE amount_pen IS NULL) AS unconverted_entries,
            COUNT(*) FILTER (WHERE data_quality = 'estimated') AS estimated_entries
        FROM finance_entries
        WHERE status = 'active' AND occurred_on >= %s AND occurred_on < %s
        """,
        (month_start, next_month_start),
    ).fetchone()
    return {
        "prepaid_topups": _money(row["prepaid_topups"]),
        "prepaid_consumption": _money(row["prepaid_consumption"]),
        "refunds": _money(row["refunds"]),
        "prepaid_refunds": _money(row["prepaid_refunds"]),
        "pending_entries": int(row["pending_entries"] or 0),
        "unconverted_entries": int(row["unconverted_entries"] or 0),
        "estimated_entries": int(row["estimated_entries"] or 0),
    }


def _finance_month_closure_payload(
    month_start: date, row: Any, movements: dict[str, Any]
) -> dict[str, Any]:
    closure = None
    expected_closing = None
    difference = None
    if row is not None:
        opening = (
            _money(row["opening_prepaid_balance"])
            if row["opening_prepaid_balance"] is not None
            else None
        )
        closing = (
            _money(row["closing_prepaid_balance"])
            if row["closing_prepaid_balance"] is not None
            else None
        )
        if opening is not None:
            expected_closing = round(
                opening
                + movements["prepaid_topups"]
                - movements["prepaid_consumption"]
                + movements["prepaid_refunds"],
                2,
            )
        if closing is not None and expected_closing is not None:
            difference = round(closing - expected_closing, 2)
        closure = {
            "opening_prepaid_balance": opening,
            "closing_prepaid_balance": closing,
            "status": str(row["status"]),
            "reconciled_at": row["reconciled_at"].isoformat()
            if row["reconciled_at"] is not None
            else None,
            "reconciled_by": str(row["reconciled_by"])
            if row["reconciled_by"] is not None
            else None,
            "notes": str(row["notes"]) if row["notes"] is not None else None,
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }
    return {
        "month": month_start.strftime("%Y-%m"),
        "closure": closure,
        "movements": movements,
        "expected_closing_prepaid_balance": expected_closing,
        "balance_difference": difference,
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
