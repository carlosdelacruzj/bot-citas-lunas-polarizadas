from __future__ import annotations

from datetime import date
from typing import Any

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _settings,
    init_database,
)

LIMA_SQL_DATE = "AT TIME ZONE 'America/Lima'"


def monthly_dashboard_summary(
    month_start: date,
    next_month_start: date,
    previous_month_start: date,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        current_payments = _payment_metrics(connection, month_start, next_month_start)
        previous_payments = _payment_metrics(connection, previous_month_start, month_start)
        orders = connection.execute(
            f"""
            SELECT COUNT(*) AS created,
                   COUNT(*) FILTER (
                       WHERE EXISTS (
                           SELECT 1 FROM reservations r
                           WHERE r.order_id = so.order_id AND r.status = 'confirmed'
                       )
                   ) AS converted
            FROM service_orders so
            WHERE (so.created_at {LIMA_SQL_DATE})::date >= %s
              AND (so.created_at {LIMA_SQL_DATE})::date < %s
            """,
            (month_start, next_month_start),
        ).fetchone()
        reservations = connection.execute(
            f"""
            SELECT COUNT(DISTINCT order_id) AS confirmed
            FROM reservations
            WHERE status = 'confirmed'
              AND (reserved_at {LIMA_SQL_DATE})::date >= %s
              AND (reserved_at {LIMA_SQL_DATE})::date < %s
            """,
            (month_start, next_month_start),
        ).fetchone()
        current_state = connection.execute(
            """
            SELECT COUNT(*) FILTER (WHERE so.status IN ('ready', 'paused')) AS active_orders,
                   COUNT(*) FILTER (
                       WHERE so.status IN ('ready', 'paused', 'reserved_payment_pending')
                         AND (wc.phone IS NULL OR BTRIM(wc.phone) = '')
                   ) AS missing_contact_count,
                   COUNT(*) FILTER (WHERE p.status = 'pending') AS pending_payments,
                   COALESCE(SUM(p.amount_agreed) FILTER (WHERE p.status = 'pending'), 0)
                       AS pending_amount
            FROM service_orders so
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = so.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            LEFT JOIN LATERAL (
                SELECT status, amount_agreed
                FROM payments
                WHERE order_id = so.order_id
                ORDER BY created_at DESC
                LIMIT 1
            ) p ON true
            """
        ).fetchone()
        daily_rows = connection.execute(
            f"""
            SELECT (paid_at {LIMA_SQL_DATE})::date AS day,
                   COALESCE(SUM(amount_paid), 0) AS amount,
                   COUNT(*) AS payments
            FROM payments
            WHERE status = 'paid'
              AND (paid_at {LIMA_SQL_DATE})::date >= %s
              AND (paid_at {LIMA_SQL_DATE})::date < %s
            GROUP BY day
            ORDER BY day
            """,
            (month_start, next_month_start),
        ).fetchall()
        source_rows = connection.execute(
            f"""
            SELECT COALESCE(NULLIF(wc.contact_source, ''), 'sin_fuente') AS source,
                   COUNT(*) FILTER (
                       WHERE (so.created_at {LIMA_SQL_DATE})::date >= %s
                         AND (so.created_at {LIMA_SQL_DATE})::date < %s
                   ) AS orders_created,
                   COUNT(*) FILTER (
                       WHERE EXISTS (
                           SELECT 1 FROM reservations r
                           WHERE r.order_id = so.order_id
                             AND r.status = 'confirmed'
                             AND (r.reserved_at {LIMA_SQL_DATE})::date >= %s
                             AND (r.reserved_at {LIMA_SQL_DATE})::date < %s
                       )
                   ) AS reservations_confirmed,
                   COALESCE(SUM((
                       SELECT SUM(p.amount_paid)
                       FROM payments p
                       WHERE p.order_id = so.order_id
                         AND p.status = 'paid'
                         AND (p.paid_at {LIMA_SQL_DATE})::date >= %s
                         AND (p.paid_at {LIMA_SQL_DATE})::date < %s
                   )), 0) AS revenue_collected
            FROM service_orders so
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = so.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            GROUP BY COALESCE(NULLIF(wc.contact_source, ''), 'sin_fuente')
            HAVING COUNT(*) FILTER (
                       WHERE (so.created_at {LIMA_SQL_DATE})::date >= %s
                         AND (so.created_at {LIMA_SQL_DATE})::date < %s
                   ) > 0
                OR COUNT(*) FILTER (
                       WHERE EXISTS (
                           SELECT 1 FROM reservations r
                           WHERE r.order_id = so.order_id
                             AND r.status = 'confirmed'
                             AND (r.reserved_at {LIMA_SQL_DATE})::date >= %s
                             AND (r.reserved_at {LIMA_SQL_DATE})::date < %s
                       )
                   ) > 0
                OR COALESCE(SUM((
                       SELECT SUM(p.amount_paid)
                       FROM payments p
                       WHERE p.order_id = so.order_id
                         AND p.status = 'paid'
                         AND (p.paid_at {LIMA_SQL_DATE})::date >= %s
                         AND (p.paid_at {LIMA_SQL_DATE})::date < %s
                   )), 0) > 0
            ORDER BY revenue_collected DESC, orders_created DESC, source
            """,
            (
                month_start,
                next_month_start,
                month_start,
                next_month_start,
                month_start,
                next_month_start,
                month_start,
                next_month_start,
                month_start,
                next_month_start,
                month_start,
                next_month_start,
            ),
        ).fetchall()
        pending_rows = connection.execute(
            """
            SELECT so.order_id, COALESCE(a.full_name, wc.display_name, 'Sin nombre') AS name,
                   wc.contact_source, p.amount_agreed, r.appointment_date,
                   r.appointment_hour
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = so.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            JOIN LATERAL (
                SELECT status, amount_agreed
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

    created = int(orders["created"] or 0)
    converted = int(orders["converted"] or 0)
    revenue = _money(current_payments["revenue"])
    previous_revenue = _money(previous_payments["revenue"])
    paid_count = int(current_payments["payments"] or 0)
    return {
        "month": month_start.strftime("%Y-%m"),
        "period": {
            "start": month_start.isoformat(),
            "end": (next_month_start.replace(day=1)).isoformat(),
        },
        "metrics": {
            "revenue_collected": revenue,
            "payments_received": paid_count,
            "reservations_confirmed": int(reservations["confirmed"] or 0),
            "orders_created": created,
            "active_orders": int(current_state["active_orders"] or 0),
            "pending_payments": int(current_state["pending_payments"] or 0),
            "pending_amount": _money(current_state["pending_amount"]),
            "average_ticket": round(revenue / paid_count, 2) if paid_count else 0.0,
            "conversion_rate": round(converted / created, 4) if created else 0.0,
        },
        "previous": {
            "month": previous_month_start.strftime("%Y-%m"),
            "revenue_collected": previous_revenue,
            "payments_received": int(previous_payments["payments"] or 0),
        },
        "daily_revenue": [
            {
                "date": row["day"].isoformat(),
                "amount": _money(row["amount"]),
                "payments": int(row["payments"]),
            }
            for row in daily_rows
        ],
        "sources": [
            {
                "source": str(row["source"]),
                "orders_created": int(row["orders_created"] or 0),
                "reservations_confirmed": int(row["reservations_confirmed"] or 0),
                "revenue_collected": _money(row["revenue_collected"]),
            }
            for row in source_rows
        ],
        "attention": {
            "missing_contact_count": int(current_state["missing_contact_count"] or 0),
            "pending_payments": [_pending_item(row) for row in pending_rows],
            "aged_active_orders": [
                {
                    "order_id": str(row["order_id"]),
                    "name": str(row["name"]),
                    "status": str(row["status"]),
                    "created_date": row["created_date"].isoformat(),
                }
                for row in aged_rows
            ],
        },
    }


def _payment_metrics(connection, start: date, end: date):
    return connection.execute(
        f"""
        SELECT COALESCE(SUM(amount_paid), 0) AS revenue, COUNT(*) AS payments
        FROM payments
        WHERE status = 'paid'
          AND (paid_at {LIMA_SQL_DATE})::date >= %s
          AND (paid_at {LIMA_SQL_DATE})::date < %s
        """,
        (start, end),
    ).fetchone()


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _pending_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": str(row["order_id"]),
        "name": str(row["name"]),
        "source": str(row["contact_source"] or "sin_fuente"),
        "amount_agreed": _money(row["amount_agreed"]),
        "reservation_date": row["appointment_date"],
        "reservation_hour": row["appointment_hour"],
    }
