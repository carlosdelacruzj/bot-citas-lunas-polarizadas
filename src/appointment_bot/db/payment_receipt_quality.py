from __future__ import annotations

from datetime import date
from typing import Any

HISTORICAL_BACKFILL_SOURCE = "historical_backfill"


def payment_receipt_date_quality(
    connection: Any,
    start: date,
    end: date,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS receipt_count,
            COUNT(*) FILTER (WHERE source = %s) AS inferred_receipt_count,
            COUNT(DISTINCT payment_id) FILTER (WHERE source = %s)
                AS inferred_payment_count,
            COALESCE(SUM(amount) FILTER (WHERE source = %s), 0) AS inferred_amount,
            COUNT(*) FILTER (WHERE source <> %s) AS exact_receipt_count,
            COALESCE(SUM(amount) FILTER (WHERE source <> %s), 0) AS exact_amount
        FROM payment_receipts
        WHERE (received_at AT TIME ZONE 'America/Lima')::date >= %s
          AND (received_at AT TIME ZONE 'America/Lima')::date < %s
        """,
        (
            HISTORICAL_BACKFILL_SOURCE,
            HISTORICAL_BACKFILL_SOURCE,
            HISTORICAL_BACKFILL_SOURCE,
            HISTORICAL_BACKFILL_SOURCE,
            HISTORICAL_BACKFILL_SOURCE,
            start,
            end,
        ),
    ).fetchone()
    cutoff = connection.execute(
        """
        SELECT MAX(created_at) AS exact_since
        FROM payment_receipts
        WHERE source = %s
        """,
        (HISTORICAL_BACKFILL_SOURCE,),
    ).fetchone()["exact_since"]

    receipt_count = int(row["receipt_count"] or 0)
    inferred_count = int(row["inferred_receipt_count"] or 0)
    exact_count = int(row["exact_receipt_count"] or 0)
    if receipt_count == 0:
        status = "no_receipts"
    elif inferred_count == 0:
        status = "exact"
    elif exact_count == 0:
        status = "inferred"
    else:
        status = "mixed"

    return {
        "status": status,
        "comparison_conclusive": inferred_count == 0,
        "exact_since": cutoff.isoformat() if cutoff is not None else None,
        "inferred_receipt_count": inferred_count,
        "inferred_payment_count": int(row["inferred_payment_count"] or 0),
        "inferred_amount": _money(row["inferred_amount"]),
        "exact_receipt_count": exact_count,
        "exact_amount": _money(row["exact_amount"]),
        "semantics": (
            "historical_backfill preserves the accumulated amount but assigns an inferred "
            "date; every other receipt source records an exact cash-event date."
        ),
    }


def _money(value: Any) -> float:
    return round(float(value or 0), 2)
