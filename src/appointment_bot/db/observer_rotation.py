from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil

from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.db.common import _connection, _database_url, init_database


@dataclass(frozen=True)
class ObserverAccount:
    account_id: str
    order_id: str
    validated_at: datetime


def defer_observer_checks(seconds: int, settings: RuntimeSettings) -> None:
    with _connection(_database_url(settings)) as connection:
        connection.execute("""
            UPDATE observer_rotation_control SET next_allowed_at = GREATEST(next_allowed_at,
                CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')) WHERE id = 1
        """, (seconds,))


def select_observer_account(settings: RuntimeSettings) -> tuple[ObserverAccount | None, int]:
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        control = connection.execute("""
            SELECT EXTRACT(EPOCH FROM next_allowed_at - CURRENT_TIMESTAMP) AS remaining
            FROM observer_rotation_control WHERE id = 1
        """).fetchone()
        if control["remaining"] > 0:
            return None, max(1, ceil(control["remaining"]))
        row = connection.execute("""
            SELECT pa.portal_account_id, validated.order_id, validated.preflight_validated_at
            FROM portal_accounts pa
            JOIN LATERAL (
                SELECT so.order_id, os.preflight_validated_at
                FROM service_orders so JOIN order_state os USING(order_id)
                WHERE so.portal_account_id = pa.portal_account_id
                  AND os.preflight_status = 'validated'
                  AND os.preflight_validated_at >= pa.updated_at
                ORDER BY os.preflight_validated_at DESC, so.order_id LIMIT 1
            ) validated ON true
            LEFT JOIN observer_account_state obs USING(portal_account_id)
            WHERE (obs.next_allowed_at IS NULL OR obs.next_allowed_at <= CURRENT_TIMESTAMP)
              AND (obs.blocked_at IS NULL OR validated.preflight_validated_at > obs.blocked_at)
              AND NOT EXISTS (
                SELECT 1 FROM service_orders so JOIN order_state os USING(order_id)
                WHERE so.portal_account_id = pa.portal_account_id AND (
                    (so.lease_owner IS NOT NULL AND so.lease_expires_at > CURRENT_TIMESTAMP)
                    OR os.next_allowed_at > CURRENT_TIMESTAMP
                    OR os.preflight_status IN ('pending', 'running', 'failed')
                    OR os.credential_failures > 0
                )
              )
              AND NOT EXISTS (
                SELECT 1 FROM reservation_attempts ra JOIN service_orders so USING(order_id)
                WHERE so.portal_account_id = pa.portal_account_id AND (
                    ra.status IN ('intent', 'pending', 'unknown')
                    OR (ra.details_json ->> 'account_cooldown_until')::timestamptz
                        > CURRENT_TIMESTAMP
                )
              )
              AND NOT EXISTS (
                SELECT 1 FROM post_appointment_automatic_reviews r
                JOIN service_orders so USING(order_id)
                WHERE so.portal_account_id = pa.portal_account_id AND r.status = 'running'
              )
            ORDER BY obs.last_observed_at ASC NULLS FIRST, pa.portal_account_id
            LIMIT 1
        """).fetchone()
        if row is None:
            return None, max(30, settings.observer_interval_min_seconds)
        return ObserverAccount(
            str(row["portal_account_id"]), str(row["order_id"]), row["preflight_validated_at"]
        ), 0


def record_observer_rotation(
    account: ObserverAccount,
    *,
    status: str,
    interval: int,
    settings: RuntimeSettings,
    block_account: bool = False,
    defense_seconds: int = 0,
    verified: bool = False,
) -> None:
    """Persist before opening a session and again after closing it; crashes retain the rest."""
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO observer_account_state (
                portal_account_id, last_observed_at, next_allowed_at, blocked_until,
                blocked_at, last_status, verified_at
            ) VALUES (%s, CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                CASE WHEN %s > 0 THEN CURRENT_TIMESTAMP + (%s * INTERVAL '1 second') END,
                CASE WHEN %s THEN CURRENT_TIMESTAMP END, %s,
                CASE WHEN %s THEN CURRENT_TIMESTAMP END)
            ON CONFLICT(portal_account_id) DO UPDATE SET
                last_observed_at = excluded.last_observed_at,
                next_allowed_at = GREATEST(observer_account_state.next_allowed_at,
                                          excluded.next_allowed_at),
                blocked_until = GREATEST(observer_account_state.blocked_until,
                                        excluded.blocked_until),
                blocked_at = excluded.blocked_at, last_status = excluded.last_status,
                verified_at = COALESCE(excluded.verified_at, observer_account_state.verified_at)
        """,
            (
                account.account_id,
                max(180, interval, defense_seconds),
                defense_seconds,
                defense_seconds,
                block_account,
                status,
                verified,
            ),
        )
        connection.execute(
            """
            UPDATE observer_rotation_control SET next_allowed_at = GREATEST(next_allowed_at,
                CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')) WHERE id = 1
        """,
            (max(30, interval, defense_seconds),),
        )
