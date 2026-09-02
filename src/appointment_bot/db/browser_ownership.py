from __future__ import annotations

from typing import Any

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _settings,
    init_database,
)


class BrowserOwnershipConflict(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return self.message


def acquire_browser_ownership(
    order_id: str,
    *,
    owner_token: str,
    purpose: str,
    lease_seconds: int,
    require_ready: bool = False,
    settings: Settings | None = None,
) -> None:
    if not owner_token.strip():
        raise ValueError("owner_token is required for browser ownership.")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be greater than zero.")
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        target = connection.execute(
            """
            SELECT so.order_id, so.portal_account_id, so.status,
                   os.preflight_status
            FROM service_orders so
            JOIN order_state os ON os.order_id = so.order_id
            WHERE so.order_id = %s
            """,
            (order_id,),
        ).fetchone()
        if target is None:
            raise BrowserOwnershipConflict("order_not_found", "La orden ya no existe.")
        if require_ready and str(target["status"]) != "ready":
            raise BrowserOwnershipConflict(
                "order_not_ready",
                "La orden ya no esta disponible para el navegador del worker.",
            )

        account_id = str(target["portal_account_id"])
        connection.execute(
            "SELECT portal_account_id FROM portal_accounts "
            "WHERE portal_account_id = %s FOR UPDATE",
            (account_id,),
        ).fetchone()

        active_lease = connection.execute(
            """
            SELECT order_id, lease_owner
            FROM service_orders
            WHERE portal_account_id = %s
              AND lease_owner IS NOT NULL
              AND lease_expires_at > CURRENT_TIMESTAMP
              AND NOT (order_id = %s AND lease_owner = %s)
            ORDER BY lease_expires_at DESC
            LIMIT 1
            """,
            (account_id, order_id, owner_token),
        ).fetchone()
        if active_lease is not None:
            lease_owner = str(active_lease["lease_owner"])
            if lease_owner.startswith("manual-session-"):
                code = "manual_session_exists"
                message = "La cuenta ya tiene una sesion manual abierta o cerrando."
            elif lease_owner.startswith(("preflight-", "post-appointment-")):
                code = "browser_job_active"
                message = "La cuenta tiene otro trabajo de navegador activo."
            else:
                code = "service_order_lease_active"
                message = "La cuenta esta siendo utilizada por el worker."
            raise BrowserOwnershipConflict(code, message)

        active_attempt = connection.execute(
            """
            SELECT ra.attempt_id
            FROM reservation_attempts ra
            JOIN service_orders so ON so.order_id = ra.order_id
            WHERE so.portal_account_id = %s
              AND ra.status IN ('intent', 'pending', 'unknown')
            LIMIT 1
            """,
            (account_id,),
        ).fetchone()
        if active_attempt is not None:
            raise BrowserOwnershipConflict(
                "active_reservation_attempt",
                "La cuenta conserva un intento de reserva activo o incierto.",
            )

        preflight = connection.execute(
            """
            SELECT so.order_id
            FROM service_orders so
            JOIN order_state os ON os.order_id = so.order_id
            WHERE so.portal_account_id = %s
              AND os.preflight_status IN ('pending', 'running')
              AND NOT (%s = 'preflight' AND so.order_id = %s)
            LIMIT 1
            """,
            (account_id, purpose, order_id),
        ).fetchone()
        if preflight is not None:
            raise BrowserOwnershipConflict(
                "preflight_in_progress",
                "La cuenta tiene una validacion de acceso pendiente o en curso.",
            )

        browser_job = connection.execute(
            """
            SELECT review.order_id
            FROM post_appointment_automatic_reviews review
            JOIN service_orders so ON so.order_id = review.order_id
            WHERE so.portal_account_id = %s
              AND review.status = 'running'
              AND NOT (%s = 'post_appointment' AND review.order_id = %s)
            LIMIT 1
            """,
            (account_id, purpose, order_id),
        ).fetchone()
        if browser_job is not None:
            raise BrowserOwnershipConflict(
                "browser_job_active",
                "La cuenta tiene otro trabajo de navegador activo.",
            )

        cursor = connection.execute(
            """
            UPDATE service_orders
            SET lease_owner = %s,
                lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
            """,
            (owner_token, lease_seconds, order_id),
        )
        if cursor.rowcount != 1:
            raise BrowserOwnershipConflict("order_not_found", "La orden ya no existe.")


def browser_ownership_summary(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT order_id, lease_owner, lease_expires_at
            FROM service_orders
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()
    return dict(row) if row is not None else None
