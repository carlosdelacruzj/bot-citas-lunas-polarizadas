from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil

from psycopg.types.json import Jsonb

from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.core.models import RunReport
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


def release_observer_credential_backoff(settings: RuntimeSettings) -> bool:
    """Release only a persisted legacy wait tied to an explicit login rejection."""
    with _connection(_database_url(settings)) as connection:
        control = connection.execute("""
            SELECT next_allowed_at FROM observer_rotation_control WHERE id = 1 FOR UPDATE
        """).fetchone()
        if control is None:
            return False
        evidence = connection.execute("""
            SELECT 1 FROM observer_account_state obs
            JOIN LATERAL (
                SELECT status, details_json, finished_at, reservation_attempted
                FROM runs WHERE details_json ->> 'mode' = 'observer'
                ORDER BY finished_at DESC LIMIT 1
            ) run ON true
            WHERE obs.last_status = 'error' AND obs.blocked_at = obs.last_observed_at
              AND obs.blocked_until = %s AND obs.blocked_until > CURRENT_TIMESTAMP
              AND run.status = 'error' AND NOT run.reservation_attempted
              AND run.details_json ->> 'observer_rotation' = 'true'
              AND run.details_json ->> 'error_type' = 'InvalidPortalCredentials'
              AND run.finished_at BETWEEN obs.blocked_at - INTERVAL '2 seconds'
                                      AND obs.blocked_at
        """, (control["next_allowed_at"],)).fetchone()
        if evidence is None:
            return False
        connection.execute("""
            UPDATE observer_rotation_control SET next_allowed_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """)
        return True


def observer_wait_seconds(settings: RuntimeSettings) -> int:
    with _connection(_database_url(settings)) as connection:
        row = connection.execute("""
            SELECT EXTRACT(EPOCH FROM next_allowed_at - CURRENT_TIMESTAMP) AS remaining
            FROM observer_rotation_control WHERE id = 1
        """).fetchone()
    return max(0, ceil(row["remaining"])) if row else 0


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
              AND NOT EXISTS (
                SELECT 1 FROM service_orders active
                WHERE active.portal_account_id = pa.portal_account_id AND active.status = 'ready'
              )
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
    access_loss_report: RunReport | None = None,
) -> None:
    """Persist before opening a session and again after closing it; crashes retain the rest."""
    with _connection(_database_url(settings)) as connection:
        if access_loss_report is not None:
            current = connection.execute("""
                SELECT updated_at FROM portal_accounts
                WHERE portal_account_id = %s FOR UPDATE
            """, (account.account_id,)).fetchone()
            observed_at = datetime.fromisoformat(access_loss_report.started_at)
            if current is None or current["updated_at"] > observed_at:
                return
            revalidated = connection.execute("""
                SELECT 1 FROM order_state os JOIN service_orders so USING(order_id)
                WHERE so.portal_account_id = %s AND os.preflight_validated_at > %s
            """, (account.account_id, observed_at)).fetchone()
            if revalidated is not None:
                return
            message = "Perdida de acceso: " + access_loss_report.message
            details = Jsonb({
                "error_type": "invalid_credentials", "source": "observer",
                "run_id": access_loss_report.run_id,
                "screenshot_path": access_loss_report.screenshot_path,
            })
            connection.execute("""
                UPDATE order_state os
                SET credential_failures = GREATEST(credential_failures, 1),
                    last_status = 'error', last_message = %s,
                    preflight_status = 'failed', preflight_message = %s,
                    preflight_details = COALESCE(preflight_details, '{}'::jsonb) || %s
                FROM service_orders so
                WHERE so.order_id = os.order_id AND so.portal_account_id = %s
            """, (message, message, details, account.account_id))
            connection.execute("""
                UPDATE service_orders SET status = 'paused', updated_at = CURRENT_TIMESTAMP
                WHERE portal_account_id = %s AND status = 'ready'
            """, (account.account_id,))
            connection.execute("""
                INSERT INTO post_appointment_reviews (
                    review_id, order_id, access_status, outcome, error_code, error_message,
                    started_at, finished_at, created_at
                )
                SELECT %s || ':' || so.order_id, so.order_id,
                    'invalid_credentials', 'access_lost', 'invalid_credentials', %s,
                    %s::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                FROM service_orders so
                WHERE so.portal_account_id = %s AND EXISTS (
                    SELECT 1 FROM reservations r
                    WHERE r.order_id = so.order_id AND r.status = 'confirmed'
                )
                ON CONFLICT (review_id) DO NOTHING
            """, (access_loss_report.run_id, message, access_loss_report.started_at,
                  account.account_id))
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
