from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _now, _settings, init_database


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

    today = date.today()
    items: list[dict[str, Any]] = []
    for row in rows:
        review_id = str(row["review_id"]) if row["review_id"] else None
        reservation_date = _parse_stored_date(row["reservation_date"])
        outcome = str(row["outcome"]) if row["outcome"] else (
            "upcoming" if reservation_date and reservation_date >= today else "review_required"
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
                "stages": stages_by_review.get(review_id or "", []),
            }
        )

    attention_outcomes = {
        "awaiting_update",
        "observation_no_progress",
        "portal_unavailable",
        "review_required",
    }
    archived_access_outcomes = {"access_lost"}
    return {
        "summary": {
            "total_confirmed": len(items),
            "active_followups": sum(
                item["outcome"] not in archived_access_outcomes for item in items
            ),
            "needs_attention": sum(item["outcome"] in attention_outcomes for item in items),
            "access_lost": sum(item["outcome"] == "access_lost" for item in items),
            "progressed_or_completed": sum(
                item["outcome"]
                in {"in_progress", "completed", "observation_with_progress"}
                for item in items
            ),
        },
        "items": items,
    }


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


def _iso(value: object) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value) if value else None


def _mask_document(value: str) -> str:
    return f"***{value[-4:]}" if len(value) > 4 else "***"
