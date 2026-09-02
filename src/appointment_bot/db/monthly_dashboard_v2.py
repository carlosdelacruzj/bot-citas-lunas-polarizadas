from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _settings, init_database
from appointment_bot.db.payment_receipt_quality import payment_receipt_date_quality
from appointment_bot.db.payment_receipt_reporting import payment_receipt_period_metrics

LIMA_TZ = ZoneInfo("America/Lima")
LIMA_SQL_DATE = "AT TIME ZONE 'America/Lima'"


def monthly_dashboard_summary_v2(
    month_start: date,
    next_month_start: date,
    previous_month_start: date,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    as_of = datetime.now(LIMA_TZ)
    coverage_end = _coverage_end(month_start, next_month_start, as_of.date())

    with _connection(_database_url(settings)) as connection:
        period_metrics = _period_metrics(connection, month_start, coverage_end)
        cohort_metrics = _cohort_metrics(connection, month_start, next_month_start)
        attention = _current_attention_snapshot(connection, as_of)
        comparisons = _comparisons(
            connection,
            month_start,
            next_month_start,
            previous_month_start,
            as_of.date(),
        )

    return {
        "contract_version": "2.0",
        "month": month_start.strftime("%Y-%m"),
        "as_of": as_of.isoformat(),
        "period_metrics": {
            "period": _period_payload(month_start, next_month_start, coverage_end),
            **period_metrics,
        },
        "cohort_metrics": {
            "cohort": {
                "created_from": month_start.isoformat(),
                "created_to_exclusive": next_month_start.isoformat(),
                "outcomes_observed_as_of": as_of.isoformat(),
            },
            **cohort_metrics,
        },
        "current_attention_snapshot": attention,
        "comparisons": comparisons,
    }


def _period_metrics(connection: Any, start: date, end: date) -> dict[str, Any]:
    row = connection.execute(
        f"""
        SELECT
            (SELECT COUNT(*)
             FROM service_orders so
             WHERE (so.created_at {LIMA_SQL_DATE})::date >= %s
               AND (so.created_at {LIMA_SQL_DATE})::date < %s) AS orders_created,
            (SELECT COUNT(*)
             FROM reservations r
             WHERE r.status = 'confirmed'
               AND (r.reserved_at {LIMA_SQL_DATE})::date >= %s
               AND (r.reserved_at {LIMA_SQL_DATE})::date < %s)
                AS confirmed_reservation_events,
            (SELECT COUNT(DISTINCT r.order_id)
             FROM reservations r
             WHERE r.status = 'confirmed'
               AND (r.reserved_at {LIMA_SQL_DATE})::date >= %s
               AND (r.reserved_at {LIMA_SQL_DATE})::date < %s)
                AS orders_reserved
        """,
        (start, end, start, end, start, end),
    ).fetchone()
    receipt_metrics = payment_receipt_period_metrics(connection, start, end)
    payments = receipt_metrics["payments_received"]
    revenue = receipt_metrics["revenue_collected"]
    receipt_date_quality = payment_receipt_date_quality(connection, start, end)
    return {
        "orders_created": int(row["orders_created"] or 0),
        "confirmed_reservation_events": int(row["confirmed_reservation_events"] or 0),
        "orders_reserved": int(row["orders_reserved"] or 0),
        **receipt_metrics,
        "receipt_date_quality": receipt_date_quality,
        "average_ticket": {
            "value": round(revenue / payments, 2) if payments else 0.0,
            "numerator": revenue,
            "denominator": payments,
        },
    }


def _cohort_metrics(connection: Any, start: date, end: date) -> dict[str, Any]:
    row = connection.execute(
        f"""
        SELECT
            COUNT(*) AS orders_created,
            COUNT(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM reservations r
                WHERE r.order_id = so.order_id AND r.status = 'confirmed'
            )) AS orders_ever_reserved,
            COUNT(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM payments p
                WHERE p.order_id = so.order_id AND p.status = 'paid'
            )) AS orders_ever_paid,
            COALESCE(SUM((
                SELECT SUM(receipt.amount)
                FROM payment_receipts receipt
                WHERE receipt.order_id = so.order_id
            )), 0) AS revenue_ever_collected,
            COUNT(*) FILTER (WHERE os.preflight_status = 'validated')
                AS validated_orders,
            COUNT(*) FILTER (
                WHERE os.preflight_status = 'validated'
                  AND EXISTS (
                      SELECT 1 FROM reservations r
                      WHERE r.order_id = so.order_id AND r.status = 'confirmed'
                  )
            ) AS validated_reserved,
            COUNT(*) FILTER (
                WHERE os.preflight_status = 'validated'
                  AND EXISTS (
                      SELECT 1 FROM payments p
                      WHERE p.order_id = so.order_id AND p.status = 'paid'
                  )
            ) AS validated_paid,
            COUNT(*) FILTER (WHERE os.preflight_status = 'not_required')
                AS legacy_not_required_orders,
            COUNT(*) FILTER (
                WHERE os.preflight_status = 'not_required'
                  AND EXISTS (
                      SELECT 1 FROM reservations r
                      WHERE r.order_id = so.order_id AND r.status = 'confirmed'
                  )
            ) AS legacy_not_required_reserved,
            COUNT(*) FILTER (
                WHERE os.preflight_status = 'not_required'
                  AND EXISTS (
                      SELECT 1 FROM payments p
                      WHERE p.order_id = so.order_id AND p.status = 'paid'
                  )
            ) AS legacy_not_required_paid
        FROM service_orders so
        LEFT JOIN order_state os ON os.order_id = so.order_id
        WHERE (so.created_at {LIMA_SQL_DATE})::date >= %s
          AND (so.created_at {LIMA_SQL_DATE})::date < %s
        """,
        (start, end),
    ).fetchone()
    acquisition_source_available = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'service_orders'
              AND column_name = 'acquisition_source'
        ) AS available
        """
    ).fetchone()["available"]
    source_expression = (
        "COALESCE(NULLIF(BTRIM(so.acquisition_source), ''), "
        "NULLIF(BTRIM(wc.contact_source), ''), 'sin_fuente')"
        if acquisition_source_available
        else "COALESCE(NULLIF(BTRIM(wc.contact_source), ''), 'sin_fuente')"
    )
    frozen_count_expression = (
        "COUNT(*) FILTER (WHERE NULLIF(BTRIM(so.acquisition_source), '') IS NOT NULL)"
        if acquisition_source_available
        else "0::bigint"
    )
    origin_counts_expression = (
        "COUNT(*) FILTER (WHERE so.acquisition_source_origin = 'order_creation') "
        "AS order_creation_source_orders, "
        "COUNT(*) FILTER (WHERE so.acquisition_source_origin = 'historical_backfill') "
        "AS historical_backfill_source_orders"
        if acquisition_source_available
        else "0::bigint AS order_creation_source_orders, "
        "0::bigint AS historical_backfill_source_orders"
    )
    source_rows = connection.execute(
        f"""
        SELECT
            {source_expression} AS source,
            COUNT(*) AS orders_created,
            {frozen_count_expression} AS frozen_source_orders,
            {origin_counts_expression},
            COUNT(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM reservations r
                WHERE r.order_id = so.order_id AND r.status = 'confirmed'
            )) AS orders_ever_reserved,
            COUNT(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM payments p
                WHERE p.order_id = so.order_id AND p.status = 'paid'
            )) AS orders_ever_paid,
            COALESCE(SUM((
                SELECT SUM(receipt.amount)
                FROM payment_receipts receipt
                WHERE receipt.order_id = so.order_id
            )), 0) AS revenue_ever_collected
        FROM service_orders so
        LEFT JOIN applicant_contacts ac
            ON ac.applicant_id = so.applicant_id AND ac.is_primary = true
        LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
        WHERE (so.created_at {LIMA_SQL_DATE})::date >= %s
          AND (so.created_at {LIMA_SQL_DATE})::date < %s
        GROUP BY {source_expression}
        ORDER BY orders_created DESC, source
        """,
        (start, end),
    ).fetchall()
    created = int(row["orders_created"] or 0)
    reserved = int(row["orders_ever_reserved"] or 0)
    paid = int(row["orders_ever_paid"] or 0)
    return {
        "orders_created": created,
        "orders_ever_reserved": reserved,
        "orders_ever_paid": paid,
        "revenue_ever_collected": _money(row["revenue_ever_collected"]),
        "reservation_conversion_rate": {
            "value": round(reserved / created, 4) if created else 0.0,
            "numerator": reserved,
            "denominator": created,
        },
        "payment_conversion_rate": {
            "value": round(paid / created, 4) if created else 0.0,
            "numerator": paid,
            "denominator": created,
        },
        "funnel": {
            "validated": {
                "orders_created": int(row["validated_orders"] or 0),
                "orders_ever_reserved": int(row["validated_reserved"] or 0),
                "orders_ever_paid": int(row["validated_paid"] or 0),
            },
            "legacy_not_required": {
                "orders_created": int(row["legacy_not_required_orders"] or 0),
                "orders_ever_reserved": int(row["legacy_not_required_reserved"] or 0),
                "orders_ever_paid": int(row["legacy_not_required_paid"] or 0),
            },
            "note": (
                "preflight_status is the latest final/current state, not an exhaustive "
                "historical event series"
            ),
        },
        "sources": [
            {
                "source": str(source["source"]),
                "orders_created": int(source["orders_created"] or 0),
                "frozen_source_orders": int(source["frozen_source_orders"] or 0),
                "order_creation_source_orders": int(
                    source["order_creation_source_orders"] or 0
                ),
                "historical_backfill_source_orders": int(
                    source["historical_backfill_source_orders"] or 0
                ),
                "orders_ever_reserved": int(source["orders_ever_reserved"] or 0),
                "orders_ever_paid": int(source["orders_ever_paid"] or 0),
                "revenue_ever_collected": _money(source["revenue_ever_collected"]),
            }
            for source in source_rows
        ],
        "source_semantics": {
            "preferred": "service_orders.acquisition_source frozen at order creation",
            "historical_backfill": (
                "existing orders copied the current primary contact source during migration; "
                "this is not proof of their original acquisition source"
            ),
            "historical_fallback": "current primary contact source when the frozen value is null",
            "frozen_storage_available": bool(acquisition_source_available),
        },
    }


def _current_attention_snapshot(connection: Any, as_of: datetime) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE so.status IN ('ready', 'paused')) AS active_orders,
            COUNT(*) FILTER (
                WHERE so.status IN ('ready', 'paused', 'reserved_payment_pending')
                  AND NOT EXISTS (
                      SELECT 1
                      FROM applicant_contacts ac
                      JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
                      WHERE ac.applicant_id = so.applicant_id
                        AND ac.is_primary = true
                        AND (
                            NULLIF(BTRIM(wc.phone), '') IS NOT NULL
                            OR NULLIF(BTRIM(wc.username), '') IS NOT NULL
                        )
                  )
            ) AS missing_contact_count,
            COUNT(*) FILTER (WHERE p.status = 'pending') AS pending_payments,
            COALESCE(SUM(
                GREATEST(p.amount_agreed - COALESCE(p.amount_paid, 0), 0)
            ) FILTER (WHERE p.status = 'pending'), 0) AS pending_amount
        FROM service_orders so
        LEFT JOIN LATERAL (
            SELECT status, amount_agreed, amount_paid
            FROM payments
            WHERE order_id = so.order_id
            ORDER BY created_at DESC
            LIMIT 1
        ) p ON true
        """
    ).fetchone()
    pending_rows = connection.execute(
        """
        SELECT so.order_id, COALESCE(a.full_name, wc.display_name, 'Sin nombre') AS name,
               wc.contact_source,
               GREATEST(p.amount_agreed - COALESCE(p.amount_paid, 0), 0)
                   AS pending_amount,
               r.appointment_date,
               r.appointment_hour
        FROM service_orders so
        JOIN applicants a ON a.applicant_id = so.applicant_id
        LEFT JOIN applicant_contacts ac
            ON ac.applicant_id = so.applicant_id AND ac.is_primary = true
        LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
        JOIN LATERAL (
            SELECT status, amount_agreed, amount_paid
            FROM payments
            WHERE order_id = so.order_id
            ORDER BY created_at DESC
            LIMIT 1
        ) p ON p.status = 'pending'
        LEFT JOIN LATERAL (
            SELECT appointment_date, appointment_hour
            FROM reservations
            WHERE order_id = so.order_id
            ORDER BY created_at DESC
            LIMIT 1
        ) r ON true
        ORDER BY r.appointment_date NULLS LAST, so.created_at
        LIMIT 12
        """
    ).fetchall()
    aged_rows = connection.execute(
        f"""
        SELECT so.order_id, COALESCE(a.full_name, wc.display_name, 'Sin nombre') AS name,
               so.status, (so.created_at {LIMA_SQL_DATE})::date AS created_date
        FROM service_orders so
        JOIN applicants a ON a.applicant_id = so.applicant_id
        LEFT JOIN applicant_contacts ac
            ON ac.applicant_id = so.applicant_id AND ac.is_primary = true
        LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
        WHERE so.status IN ('ready', 'paused')
          AND so.created_at < CURRENT_TIMESTAMP - INTERVAL '7 days'
        ORDER BY so.created_at
        LIMIT 12
        """
    ).fetchall()
    return {
        "as_of": as_of.isoformat(),
        "active_orders": int(row["active_orders"] or 0),
        "missing_contact_count": int(row["missing_contact_count"] or 0),
        "valid_contact_rule": "primary phone or primary WhatsApp username",
        "pending_payments": int(row["pending_payments"] or 0),
        "pending_amount": _money(row["pending_amount"]),
        "pending_payment_items": [
            {
                "order_id": str(item["order_id"]),
                "name": str(item["name"]),
                "source": str(item["contact_source"] or "sin_fuente"),
                "pending_amount": _money(item["pending_amount"]),
                "reservation_date": item["appointment_date"],
                "reservation_hour": item["appointment_hour"],
            }
            for item in pending_rows
        ],
        "aged_active_orders": [
            {
                "order_id": str(item["order_id"]),
                "name": str(item["name"]),
                "status": str(item["status"]),
                "created_date": item["created_date"].isoformat(),
            }
            for item in aged_rows
        ],
        "list_limit": 12,
    }


def _comparisons(
    connection: Any,
    month_start: date,
    next_month_start: date,
    previous_month_start: date,
    today: date,
) -> dict[str, Any]:
    current_month = today.replace(day=1)
    same_day_window: dict[str, Any] | None = None
    if month_start == current_month:
        elapsed_days = today.day
        previous_end = min(
            previous_month_start + timedelta(days=elapsed_days),
            month_start,
        )
        same_day_window = {
            "elapsed_days": elapsed_days,
            "selected": {
                "period": _period_payload(month_start, next_month_start, today + timedelta(days=1)),
                "metrics": _period_metrics(connection, month_start, today + timedelta(days=1)),
            },
            "previous": {
                "period": _period_payload(previous_month_start, month_start, previous_end),
                "metrics": _period_metrics(connection, previous_month_start, previous_end),
            },
        }

    if next_month_start <= current_month:
        closed_end = next_month_start
        closed_start = month_start
    else:
        closed_end = current_month
        closed_start = _shift_month(closed_end, -1)
    prior_closed_start = _shift_month(closed_start, -1)
    closed_months = {
        "selected": {
            "period": _period_payload(closed_start, closed_end, closed_end),
            "metrics": _period_metrics(connection, closed_start, closed_end),
        },
        "previous": {
            "period": _period_payload(prior_closed_start, closed_start, closed_start),
            "metrics": _period_metrics(connection, prior_closed_start, closed_start),
        },
    }
    return {
        "same_day_window": same_day_window,
        "closed_months": closed_months,
    }


def _coverage_end(month_start: date, next_month_start: date, today: date) -> date:
    if month_start > today:
        return month_start
    if next_month_start <= today:
        return next_month_start
    return min(today + timedelta(days=1), next_month_start)


def _period_payload(start: date, end: date, coverage_end: date) -> dict[str, Any]:
    return {
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "coverage_end_exclusive": coverage_end.isoformat(),
        "is_closed": coverage_end >= end,
    }


def _shift_month(value: date, delta: int) -> date:
    month_index = value.year * 12 + value.month - 1 + delta
    return date(month_index // 12, month_index % 12 + 1, 1)


def _money(value: Any) -> float:
    return round(float(value or 0), 2)
