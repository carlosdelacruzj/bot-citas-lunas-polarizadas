from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _now, _settings, init_database

LIMA_TZ = ZoneInfo("America/Lima")
POST_APPOINTMENT_AUTOMATION_TIME = time(20, 0)
POST_APPOINTMENT_AUTOMATION_DAILY_LIMIT = 20
POST_APPOINTMENT_AUTOMATION_MAX_AGE_DAYS = 30
POST_APPOINTMENT_AUTOMATION_LOCK_ID = 1_047_296_812
TERMINAL_POST_APPOINTMENT_OUTCOMES = frozenset({"completed", "access_lost"})
TECHNICAL_AUTOMATION_ERROR_CODES = frozenset(
    {"portal_error", "workflow_unavailable", "automatic_review_error"}
)


def get_post_appointment_target(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT r.reservation_id, r.order_id, r.appointment_date, r.appointment_hour,
                   r.program_expediente, r.program_plate
            FROM reservations r
            WHERE r.order_id = %s AND r.status = 'confirmed'
            ORDER BY r.created_at DESC
            LIMIT 1
            """,
            (order_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def record_post_appointment_review(
    *,
    order_id: str,
    access_status: str,
    outcome: str,
    appointment_date: date | None,
    appointment_hour: str | None,
    stages: list[dict[str, Any]],
    observation_count: int,
    later_progress_observed: bool,
    started_at: datetime,
    finished_at: datetime,
    error_code: str | None = None,
    error_message: str | None = None,
    settings: Settings | None = None,
) -> str:
    settings = _settings(settings)
    init_database(settings)
    review_id = f"post-appointment-{uuid4().hex}"
    created_at = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO post_appointment_reviews (
                review_id, order_id, access_status, outcome, appointment_date,
                appointment_hour, stage_count, observation_count,
                later_progress_observed, error_code, error_message,
                started_at, finished_at, created_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            """,
            (
                review_id,
                order_id,
                access_status,
                outcome,
                appointment_date,
                appointment_hour,
                len(stages),
                observation_count,
                later_progress_observed,
                error_code,
                error_message,
                started_at,
                finished_at,
                created_at,
            ),
        )
        for index, stage in enumerate(stages):
            connection.execute(
                """
                INSERT INTO post_appointment_stage_snapshots (
                    review_id, stage_index, stage_key, stage_label, stage_date,
                    stage_hour, status_text, message_present, message_class,
                    message_text, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    review_id,
                    index,
                    stage["stage_key"],
                    stage["stage_label"],
                    stage.get("stage_date"),
                    stage.get("stage_hour"),
                    stage.get("status_text"),
                    bool(stage.get("message_present")),
                    stage.get("message_class", "none"),
                    stage.get("message_text"),
                    created_at,
                ),
            )
    return review_id


def list_post_appointment_followups(
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT so.order_id, so.parent_order_id,
                   COALESCE(NULLIF(a.full_name, ''), a.document_number) AS applicant_name,
                   a.document_number,
                   reservation.reservation_id,
                   reservation.site,
                   reservation.appointment_day AS reservation_day,
                   reservation.appointment_date AS reservation_date,
                   reservation.appointment_hour AS reservation_hour,
                   COALESCE(reservation.program_expediente, so.program_expediente)
                       AS program_expediente,
                   COALESCE(reservation.program_plate, so.program_plate) AS program_plate,
                   review.review_id, review.access_status, review.outcome,
                   review.appointment_date AS reviewed_appointment_date,
                   review.appointment_hour AS reviewed_appointment_hour,
                   review.stage_count, review.observation_count,
                   review.later_progress_observed, review.error_code,
                   review.error_message, review.finished_at
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN LATERAL (
                SELECT r.*
                FROM reservations r
                WHERE r.order_id = so.order_id AND r.status = 'confirmed'
                ORDER BY r.created_at DESC
                LIMIT 1
            ) reservation ON true
            LEFT JOIN LATERAL (
                SELECT pr.*
                FROM post_appointment_reviews pr
                WHERE pr.order_id = so.order_id
                  AND (
                      pr.appointment_date IS NULL
                      OR pr.appointment_date = reservation.appointment_day
                  )
                ORDER BY pr.finished_at DESC
                LIMIT 1
            ) review ON true
            ORDER BY COALESCE(review.finished_at, reservation.reserved_at) ASC
            """
        ).fetchall()
        review_ids = [str(row["review_id"]) for row in rows if row["review_id"]]
        stage_rows = (
            connection.execute(
                """
                SELECT review_id, stage_index, stage_key, stage_label, stage_date,
                       stage_hour, status_text, message_present, message_class, message_text
                FROM post_appointment_stage_snapshots
                WHERE review_id = ANY(%s)
                ORDER BY review_id, stage_index
                """,
                (review_ids,),
            ).fetchall()
            if review_ids
            else []
        )

    stages_by_review: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stage in stage_rows:
        stages_by_review[str(stage["review_id"])].append(
            {
                "stage_key": str(stage["stage_key"]),
                "stage_label": str(stage["stage_label"]),
                "stage_date": _iso(stage["stage_date"]),
                "stage_hour": stage["stage_hour"],
                "status_text": stage["status_text"],
                "message_present": bool(stage["message_present"]),
                "message_class": str(stage["message_class"]),
                "message_text": stage["message_text"],
            }
        )

    now = datetime.now(LIMA_TZ)
    today = now.date()
    items: list[dict[str, Any]] = []
    for row in rows:
        review_id = str(row["review_id"]) if row["review_id"] else None
        reservation_date = _parse_stored_date(row["reservation_day"]) or _parse_stored_date(
            row["reservation_date"]
        )
        stored_outcome = str(row["outcome"]) if row["outcome"] else None
        outcome = stored_outcome or (
            "upcoming" if reservation_date and reservation_date >= today else "review_required"
        )
        if reservation_date and reservation_date < today and outcome == "upcoming":
            outcome = "review_required"
        last_reviewed_at = _as_datetime(row["finished_at"])
        review_freshness = _review_freshness(
            appointment_date=reservation_date,
            outcome=outcome,
            last_reviewed_at=last_reviewed_at,
            today=today,
        )
        items.append(
            {
                "order_id": str(row["order_id"]),
                "parent_order_id": row["parent_order_id"],
                "applicant_name": str(row["applicant_name"]),
                "document_number_masked": _mask_document(str(row["document_number"])),
                "reservation_id": str(row["reservation_id"]),
                "site": row["site"],
                "program_expediente": row["program_expediente"],
                "program_plate": row["program_plate"],
                "appointment_date": _iso(row["reviewed_appointment_date"])
                or _iso(reservation_date)
                or str(row["reservation_date"] or ""),
                "appointment_hour": row["reviewed_appointment_hour"]
                or row["reservation_hour"],
                "review_id": review_id,
                "access_status": (
                    str(row["access_status"]) if row["access_status"] else "not_checked"
                ),
                "outcome": outcome,
                "observation_count": int(row["observation_count"] or 0),
                "later_progress_observed": bool(row["later_progress_observed"]),
                "error_code": row["error_code"],
                "error_message": row["error_message"],
                "last_reviewed_at": _iso(row["finished_at"]),
                "review_freshness": review_freshness,
                "next_automatic_review_at": _next_automatic_review_at(
                    appointment_date=reservation_date,
                    outcome=outcome,
                    last_reviewed_at=last_reviewed_at,
                    now=now,
                ),
                "stages": stages_by_review.get(review_id or "", []),
            }
        )

    attention_outcomes = {
        "awaiting_update",
        "observation_no_progress",
        "portal_unavailable",
        "review_required",
    }
    terminal_outcomes = TERMINAL_POST_APPOINTMENT_OUTCOMES
    automation = post_appointment_automation_status(
        service_date=today,
        settings=settings,
    )
    return {
        "summary": {
            "total_confirmed": len(items),
            "active_followups": sum(
                item["outcome"] not in terminal_outcomes for item in items
            ),
            "needs_attention": sum(item["outcome"] in attention_outcomes for item in items),
            "access_lost": sum(item["outcome"] == "access_lost" for item in items),
            "progressed_or_completed": sum(
                item["outcome"]
                in {"in_progress", "completed", "observation_with_progress"}
                for item in items
            ),
        },
        "automation": automation,
        "items": items,
    }


def claim_next_post_appointment_automatic_review(
    *,
    service_date: date,
    daily_limit: int = POST_APPOINTMENT_AUTOMATION_DAILY_LIMIT,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    claimed_at = _now()
    oldest_appointment_day = service_date - timedelta(
        days=POST_APPOINTMENT_AUTOMATION_MAX_AGE_DAYS
    )
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (POST_APPOINTMENT_AUTOMATION_LOCK_ID,),
        )
        attempted = connection.execute(
            """
            SELECT count(*) AS total
            FROM post_appointment_automatic_reviews
            WHERE service_date = %s
            """,
            (service_date,),
        ).fetchone()
        if int(attempted["total"] or 0) >= daily_limit:
            return None
        if _automatic_review_breaker_open(connection, service_date):
            return None
        row = connection.execute(
            """
            WITH latest_reservation AS (
                SELECT DISTINCT ON (r.order_id)
                       r.reservation_id, r.order_id, r.appointment_day, r.created_at
                FROM reservations r
                JOIN service_orders so ON so.order_id = r.order_id
                WHERE r.status = 'confirmed'
                  AND (
                      so.closure_reason IS NULL
                      OR so.closure_reason NOT IN (
                          'client_withdrew', 'external_slot', 'duplicate',
                          'not_serviceable', 'uncollectible'
                      )
                  )
                ORDER BY r.order_id, r.created_at DESC
            ), eligible AS (
                SELECT reservation.reservation_id, reservation.order_id,
                       review.outcome, review.finished_at
                FROM latest_reservation reservation
                LEFT JOIN LATERAL (
                    SELECT pr.outcome, pr.finished_at
                    FROM post_appointment_reviews pr
                    WHERE pr.order_id = reservation.order_id
                      AND (
                          pr.appointment_date IS NULL
                          OR pr.appointment_date = reservation.appointment_day
                      )
                    ORDER BY pr.finished_at DESC
                    LIMIT 1
                ) review ON true
                WHERE reservation.appointment_day BETWEEN %s AND %s
                  AND COALESCE(review.outcome, '') NOT IN ('completed', 'access_lost')
                  AND NOT EXISTS (
                      SELECT 1
                      FROM post_appointment_reviews today_review
                      WHERE today_review.order_id = reservation.order_id
                        AND (
                            today_review.appointment_date IS NULL
                            OR today_review.appointment_date = reservation.appointment_day
                        )
                        AND (today_review.finished_at AT TIME ZONE 'America/Lima')::date = %s
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM post_appointment_automatic_reviews automatic_review
                      WHERE automatic_review.service_date = %s
                        AND automatic_review.reservation_id = reservation.reservation_id
                  )
                ORDER BY
                    CASE WHEN review.finished_at IS NULL THEN 0 ELSE 1 END,
                    CASE COALESCE(review.outcome, 'review_required')
                        WHEN 'review_required' THEN 0
                        WHEN 'upcoming' THEN 0
                        WHEN 'portal_unavailable' THEN 1
                        WHEN 'observation_no_progress' THEN 2
                        WHEN 'awaiting_update' THEN 3
                        WHEN 'in_progress' THEN 4
                        WHEN 'observation_with_progress' THEN 5
                        ELSE 6
                    END,
                    review.finished_at ASC NULLS FIRST,
                    reservation.appointment_day ASC,
                    reservation.created_at ASC
                LIMIT 1
            )
            INSERT INTO post_appointment_automatic_reviews (
                service_date, reservation_id, order_id, status, claimed_at
            )
            SELECT %s, eligible.reservation_id, eligible.order_id, 'running', %s
            FROM eligible
            RETURNING reservation_id, order_id, claimed_at
            """,
            (
                oldest_appointment_day,
                service_date - timedelta(days=1),
                service_date,
                service_date,
                service_date,
                claimed_at,
            ),
        ).fetchone()
    return dict(row) if row is not None else None


def finish_post_appointment_automatic_review(
    *,
    service_date: date,
    reservation_id: str,
    status: str,
    review_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    settings: Settings | None = None,
) -> None:
    if status not in {"completed", "failed", "skipped"}:
        raise ValueError("Automatic post-appointment status must be terminal.")
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE post_appointment_automatic_reviews
            SET status = %s, review_id = %s, error_code = %s, error_message = %s,
                finished_at = %s
            WHERE service_date = %s AND reservation_id = %s AND status = 'running'
            RETURNING reservation_id
            """,
            (
                status,
                review_id,
                error_code,
                error_message,
                _now(),
                service_date,
                reservation_id,
            ),
        ).fetchone()
    if row is None:
        raise RuntimeError("La revisión automática ya no estaba activa.")


def fail_stale_post_appointment_automatic_reviews(
    *,
    service_date: date,
    settings: Settings | None = None,
) -> int:
    settings = _settings(settings)
    init_database(settings)
    stale_before = datetime.now(UTC) - timedelta(hours=2)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            UPDATE post_appointment_automatic_reviews
            SET status = 'failed', error_code = 'scheduler_interrupted',
                error_message = 'La revisión automática fue interrumpida y no se reintentará hoy.',
                finished_at = %s
            WHERE status = 'running'
              AND (service_date < %s OR claimed_at < %s)
            RETURNING reservation_id
            """,
            (_now(), service_date, stale_before),
        ).fetchall()
    return len(rows)


def post_appointment_automation_status(
    *,
    service_date: date,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    oldest_appointment_day = service_date - timedelta(
        days=POST_APPOINTMENT_AUTOMATION_MAX_AGE_DAYS
    )
    with _connection(_database_url(settings)) as connection:
        counters = connection.execute(
            """
            SELECT count(*) FILTER (WHERE status = 'running') AS running,
                   count(*) FILTER (WHERE status = 'completed') AS completed,
                   count(*) FILTER (WHERE status = 'failed') AS failed,
                   max(COALESCE(finished_at, claimed_at)) AS last_run_at
            FROM post_appointment_automatic_reviews
            WHERE service_date = %s
            """,
            (service_date,),
        ).fetchone()
        due = connection.execute(
            """
            WITH latest_reservation AS (
                SELECT DISTINCT ON (r.order_id)
                       r.reservation_id, r.order_id, r.appointment_day
                FROM reservations r
                JOIN service_orders so ON so.order_id = r.order_id
                WHERE r.status = 'confirmed'
                  AND (
                      so.closure_reason IS NULL
                      OR so.closure_reason NOT IN (
                          'client_withdrew', 'external_slot', 'duplicate',
                          'not_serviceable', 'uncollectible'
                      )
                  )
                ORDER BY r.order_id, r.created_at DESC
            )
            SELECT count(*) AS total
            FROM latest_reservation reservation
            LEFT JOIN LATERAL (
                SELECT pr.outcome
                FROM post_appointment_reviews pr
                WHERE pr.order_id = reservation.order_id
                  AND (
                      pr.appointment_date IS NULL
                      OR pr.appointment_date = reservation.appointment_day
                  )
                ORDER BY pr.finished_at DESC
                LIMIT 1
            ) review ON true
            WHERE reservation.appointment_day BETWEEN %s AND %s
              AND COALESCE(review.outcome, '') NOT IN ('completed', 'access_lost')
              AND NOT EXISTS (
                  SELECT 1
                  FROM post_appointment_reviews today_review
                  WHERE today_review.order_id = reservation.order_id
                    AND (
                        today_review.appointment_date IS NULL
                        OR today_review.appointment_date = reservation.appointment_day
                    )
                    AND (today_review.finished_at AT TIME ZONE 'America/Lima')::date = %s
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM post_appointment_automatic_reviews automatic_review
                  WHERE automatic_review.service_date = %s
                    AND automatic_review.reservation_id = reservation.reservation_id
              )
            """,
            (
                oldest_appointment_day,
                service_date - timedelta(days=1),
                service_date,
                service_date,
            ),
        ).fetchone()
        breaker_open = _automatic_review_breaker_open(connection, service_date)
    return {
        "enabled": True,
        "timezone": "America/Lima",
        "time": POST_APPOINTMENT_AUTOMATION_TIME.isoformat(timespec="minutes"),
        "daily_limit": POST_APPOINTMENT_AUTOMATION_DAILY_LIMIT,
        "due_count": int(due["total"] or 0),
        "running": int(counters["running"] or 0),
        "completed_today": int(counters["completed"] or 0),
        "failed_today": int(counters["failed"] or 0),
        "last_run_at": _iso(counters["last_run_at"]),
        "breaker_open": breaker_open,
        "breaker_reason": (
            "three_consecutive_technical_failures" if breaker_open else None
        ),
    }


def _automatic_review_breaker_open(connection: Any, service_date: date) -> bool:
    rows = connection.execute(
        """
        SELECT status, error_code
        FROM post_appointment_automatic_reviews
        WHERE service_date = %s AND status <> 'running'
        ORDER BY claimed_at DESC
        LIMIT 3
        """,
        (service_date,),
    ).fetchall()
    return len(rows) == 3 and all(
        row["status"] == "failed"
        and str(row["error_code"] or "") in TECHNICAL_AUTOMATION_ERROR_CODES
        for row in rows
    )


def _parse_stored_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _review_freshness(
    *,
    appointment_date: date | None,
    outcome: str,
    last_reviewed_at: datetime | None,
    today: date,
) -> str:
    if outcome in TERMINAL_POST_APPOINTMENT_OUTCOMES:
        return "not_applicable"
    if appointment_date is None or appointment_date >= today:
        return "not_applicable"
    if last_reviewed_at is None:
        return "not_reviewed"
    reviewed_on = last_reviewed_at.astimezone(LIMA_TZ).date()
    return "current" if reviewed_on == today else "stale"


def _next_automatic_review_at(
    *,
    appointment_date: date | None,
    outcome: str,
    last_reviewed_at: datetime | None,
    now: datetime,
) -> str | None:
    if outcome in TERMINAL_POST_APPOINTMENT_OUTCOMES or appointment_date is None:
        return None
    first_eligible_day = appointment_date + timedelta(days=1)
    last_eligible_day = appointment_date + timedelta(
        days=POST_APPOINTMENT_AUTOMATION_MAX_AGE_DAYS
    )
    if now.date() > last_eligible_day:
        return None
    if now.date() < first_eligible_day:
        target_day = first_eligible_day
    elif (
        last_reviewed_at is not None
        and last_reviewed_at.astimezone(LIMA_TZ).date() == now.date()
    ):
        target_day = now.date() + timedelta(days=1)
        if target_day > last_eligible_day:
            return None
    else:
        target_day = now.date()
    return datetime.combine(
        target_day,
        POST_APPOINTMENT_AUTOMATION_TIME,
        tzinfo=LIMA_TZ,
    ).isoformat()


def _iso(value: object) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value) if value else None


def _mask_document(value: str) -> str:
    return f"***{value[-4:]}" if len(value) > 4 else "***"
