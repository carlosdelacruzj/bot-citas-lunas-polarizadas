from __future__ import annotations

from datetime import date
from typing import Any

PAYMENTS_RECEIVED_SEMANTICS = (
    "payments_received counts signed payment_receipts movements in the period; "
    "revenue_collected is their signed sum, and daily_revenue uses the same rows."
)


def payment_receipt_period_metrics(
    connection: Any,
    start: date,
    end: date,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT COUNT(*) AS receipt_count,
               COUNT(DISTINCT payment_id) AS payment_count,
               COUNT(DISTINCT order_id) AS order_count,
               COALESCE(SUM(amount), 0) AS amount
        FROM payment_receipts
        WHERE (received_at AT TIME ZONE 'America/Lima')::date >= %s
          AND (received_at AT TIME ZONE 'America/Lima')::date < %s
        """,
        (start, end),
    ).fetchone()
    daily_rows = connection.execute(
        """
        SELECT (received_at AT TIME ZONE 'America/Lima')::date AS day,
               COALESCE(SUM(amount), 0) AS amount,
               COUNT(*) AS receipt_count
        FROM payment_receipts
        WHERE (received_at AT TIME ZONE 'America/Lima')::date >= %s
          AND (received_at AT TIME ZONE 'America/Lima')::date < %s
        GROUP BY day
        ORDER BY day
        """,
        (start, end),
    ).fetchall()
    return {
        "payments_received": int(row["receipt_count"] or 0),
        "distinct_payments": int(row["payment_count"] or 0),
        "orders_with_receipts": int(row["order_count"] or 0),
        "revenue_collected": _money(row["amount"]),
        "payments_received_semantics": PAYMENTS_RECEIVED_SEMANTICS,
        "daily_revenue": [
            {
                "date": daily["day"].isoformat(),
                "amount": _money(daily["amount"]),
                "payments": int(daily["receipt_count"] or 0),
            }
            for daily in daily_rows
        ],
    }


def _money(value: Any) -> float:
    return round(float(value or 0), 2)
