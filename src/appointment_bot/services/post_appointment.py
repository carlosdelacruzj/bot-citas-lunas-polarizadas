from __future__ import annotations

import logging
import re
import threading
import unicodedata
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings, load_settings
from appointment_bot.db.order_credentials import get_service_order_runtime
from appointment_bot.db.post_appointment import (
    get_post_appointment_target,
    list_post_appointment_followups,
    record_post_appointment_review,
)
from appointment_bot.reports.run_reporting import settings_for_order
from appointment_bot.reservation_engine.appointments import AppointmentWorkflowUnavailable
from appointment_bot.reservation_engine.login import InvalidPortalCredentials, login
from appointment_bot.reservation_engine.programs import open_program_detail_for_review
from appointment_bot.reservation_engine.stages import ProcessStage, read_process_stages

logger = logging.getLogger(__name__)

LIMA_TZ = ZoneInfo("America/Lima")
POST_APPOINTMENT_STAGE_KEYS = {"peritaje_vehicular", "peritaje_lunas", "validacion"}
_ACTIVE_REVIEWS: set[str] = set()
_ACTIVE_REVIEWS_LOCK = threading.Lock()
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")


class PostAppointmentReviewConflict(RuntimeError):
    pass


def review_post_appointment_order(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or load_settings(require_login=False)
    target = get_post_appointment_target(order_id, settings=settings)
    if target is None:
        raise ValueError("La orden no tiene una cita confirmada registrada.")
    order = get_service_order_runtime(order_id, settings=settings)
    if order is None:
        raise ValueError("La orden ya no existe.")

    with _ACTIVE_REVIEWS_LOCK:
        if order_id in _ACTIVE_REVIEWS:
            raise PostAppointmentReviewConflict("La orden ya se está revisando.")
        _ACTIVE_REVIEWS.add(order_id)

    started_at = datetime.now(UTC)
    appointment_date = _parse_date(target.get("appointment_date"))
    appointment_hour = _clean_text(target.get("appointment_hour"))
    access_status = "success"
    outcome = "review_required"
    stages: list[dict[str, Any]] = []
    observation_count = 0
    later_progress_observed = False
    error_code: str | None = None
    error_message: str | None = None

    review_settings = replace(
        settings_for_order(
            settings,
            username=order.username,
            password=order.password,
            document_type=order.document_type,
        ),
        headless=True,
        auto_reserve=False,
        monitor_window_seconds=0,
        telegram_notify_unavailable=False,
        artifact_prefix=f"post-appointment-{order_id}",
    )
    try:
        with open_page(review_settings, headless=True, block_heavy_assets=True) as page:
            login(page, review_settings)
            page = open_program_detail_for_review(
                page,
                program_expediente=(
                    target.get("program_expediente") or order.program_expediente
                ),
                program_plate=target.get("program_plate") or order.program_plate,
            )
            process_stages = read_process_stages(page)
            stages = [_sanitize_stage(stage) for stage in process_stages]
            observation_count = sum(
                stage["message_class"] == "observation" for stage in stages
            )
            later_progress_observed = _has_post_appointment_progress(stages)
            appointment_stage = next(
                (stage for stage in stages if stage["stage_key"] == "separa_cita_peritaje"),
                None,
            )
            if appointment_stage is not None:
                appointment_date = appointment_stage.get("stage_date") or appointment_date
                appointment_hour = appointment_stage.get("stage_hour") or appointment_hour
            outcome = _classify_outcome(
                stages,
                appointment_date=appointment_date,
                observation_count=observation_count,
                later_progress_observed=later_progress_observed,
            )
    except InvalidPortalCredentials:
        access_status = "invalid_credentials"
        outcome = "access_lost"
        error_code = "invalid_credentials"
        error_message = "El portal rechazó las credenciales; posiblemente fueron cambiadas."
    except AppointmentWorkflowUnavailable:
        access_status = "workflow_unavailable"
        outcome = "review_required"
        error_code = "workflow_unavailable"
        error_message = "El portal no mostró el trámite esperado para una revisión automática."
    except Exception:
        logger.exception("Post-appointment review failed: order_id=%s", order_id)
        access_status = "portal_error"
        outcome = "portal_unavailable"
        error_code = "portal_error"
        error_message = "No se pudo completar la consulta de solo lectura en el portal."
    finally:
        finished_at = datetime.now(UTC)
        try:
            review_id = record_post_appointment_review(
                order_id=order_id,
                access_status=access_status,
                outcome=outcome,
                appointment_date=appointment_date,
                appointment_hour=appointment_hour,
                stages=stages,
                observation_count=observation_count,
                later_progress_observed=later_progress_observed,
                error_code=error_code,
                error_message=error_message,
                started_at=started_at,
                finished_at=finished_at,
                settings=settings,
            )
        finally:
            with _ACTIVE_REVIEWS_LOCK:
                _ACTIVE_REVIEWS.discard(order_id)

    payload = list_post_appointment_followups(settings=settings)
    item = next(item for item in payload["items"] if item["order_id"] == order_id)
    item["review_id"] = review_id
    return item


def _sanitize_stage(stage: ProcessStage) -> dict[str, Any]:
    message = stage.message.strip()
    message_class = _classify_message(message)
    parsed_date = _parse_date(stage.date)
    hour_match = _TIME_RE.search(stage.date)
    return {
        "stage_key": _stage_key(stage.stage),
        "stage_label": stage.stage.strip() or "Etapa sin nombre",
        "stage_date": parsed_date,
        "stage_hour": hour_match.group(0) if hour_match else None,
        "status_text": _clean_text(stage.status),
        "message_present": bool(message),
        "message_class": message_class,
        "message_text": _clean_text(message),
    }


def _classify_message(message: str) -> str:
    normalized = _normalize(message)
    if not normalized:
        return "none"
    if normalized == "ok" or normalized.startswith("ok "):
        return "ok"
    return "observation"


def _classify_outcome(
    stages: list[dict[str, Any]],
    *,
    appointment_date: date | None,
    observation_count: int,
    later_progress_observed: bool,
) -> str:
    final_stage = next((stage for stage in stages if stage["stage_key"] == "validacion"), None)
    final_status = _normalize(final_stage.get("status_text") if final_stage else "")
    if final_status in {"atendido", "completado", "aprobado"}:
        return "completed"
    if observation_count:
        return "observation_with_progress" if later_progress_observed else "observation_no_progress"
    if later_progress_observed:
        return "in_progress"
    today = datetime.now(LIMA_TZ).date()
    if appointment_date and appointment_date >= today:
        return "upcoming"
    if appointment_date and appointment_date < today:
        return "awaiting_update"
    return "review_required"


def _has_post_appointment_progress(stages: list[dict[str, Any]]) -> bool:
    for stage in stages:
        if stage["stage_key"] not in POST_APPOINTMENT_STAGE_KEYS:
            continue
        status = _normalize(stage.get("status_text"))
        if stage.get("stage_date") or status not in {"", "pendiente", "programado"}:
            return True
    return False


def _stage_key(value: str) -> str:
    normalized = _normalize(value)
    return "_".join(part for part in re.split(r"[^a-z0-9]+", normalized) if part)


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(text.encode("ascii", "ignore").decode().casefold().split())


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None


def _clean_text(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


__all__ = [
    "PostAppointmentReviewConflict",
    "review_post_appointment_order",
]
