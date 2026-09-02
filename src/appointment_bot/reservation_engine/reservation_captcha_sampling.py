from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from appointment_bot.config import Settings
from appointment_bot.reservation_engine.appointments import AppointmentWorkflowCancelled
from appointment_bot.reservation_engine.ports import AlertSink, CaptchaAuthority
from appointment_bot.reservation_engine.reservation_captcha_capture import (
    captcha_submission_image_path,
    save_reservation_captcha_image,
)
from appointment_bot.reservation_engine.reservation_captcha_math import (
    has_reservation_math_captcha,
)
from appointment_bot.reservation_engine.reservation_captcha_refresh import (
    refresh_reservation_captcha,
)

logger = logging.getLogger(__name__)


def collect_reservation_captcha_training_samples(
    page: Page,
    settings: Settings,
    *,
    cancel_event: threading.Event | None,
    can_submit: Callable[[], bool] | None,
    validate_selection: Callable[[], None],
    detection_origin: object,
    captcha_audit: dict[str, Any],
    attempt_number: int,
    run_id: str | None,
    order_id: str | None,
    event_context: str | None = None,
    captcha_authority: CaptchaAuthority | None = None,
    alert_sink: AlertSink | None = None,
) -> None:
    if has_reservation_math_captcha(page):
        captcha_audit["captcha_training_sample_limit"] = 1
        captcha_audit["captcha_training_samples_collected"] = 0
        captcha_audit["captcha_training_skipped_reason"] = "html_math"
        logger.info("Skipping five-character CAPTCHA sampling for HTML math captcha")
        return

    sample_limit = _resolve_sample_limit(settings, captcha_authority)
    extra_sample_count = sample_limit - 1
    if extra_sample_count <= 0:
        return

    started = time.monotonic()
    sample_paths: list[str] = []
    sample_timings: list[dict[str, Any]] = []
    shadow_event_ids: list[str] = []
    logger.info(
        "Collecting %s extra reservation CAPTCHA samples before 2Captcha",
        extra_sample_count,
    )

    for sample_number in range(1, extra_sample_count + 1):
        sample_started = time.monotonic()
        _ensure_reservation_can_continue(cancel_event, can_submit)
        validate_selection()
        sample_audit: dict[str, Any] = {}
        capture_started = time.monotonic()
        try:
            captured_path = save_reservation_captcha_image(
                page,
                settings,
                (
                    "04-reserva-captcha-entrenamiento-"
                    f"{attempt_number}-{sample_number}"
                ),
                captcha_audit=sample_audit,
                alert_sink=alert_sink,
            )
            sample_path = captcha_submission_image_path(captured_path, sample_audit)
        except Exception as exc:
            logger.warning(
                "Could not collect reservation CAPTCHA training sample %s: %s",
                sample_number,
                exc,
            )
            break
        capture_duration_ms = round(
            max(time.monotonic() - capture_started, 0.0) * 1000,
            3,
        )

        sample_paths.append(str(sample_path))
        if run_id:
            event_namespace = (
                f"{run_id}:{order_id or 'observer'}"
                f"{f':{event_context}' if event_context else ''}"
            )
            event_id = (
                f"{event_namespace}:captcha-{attempt_number}"
                f"-training-{sample_number}"
            )
            try:
                if captcha_authority is None:
                    raise RuntimeError(
                        "CaptchaAuthority is required for CAPTCHA training samples."
                    )
                enqueued = captcha_authority.enqueue_prediction(
                    event_id=event_id,
                    image_path=str(Path(sample_path).resolve()),
                    metadata={
                        "run_id": run_id,
                        "order_id": order_id,
                        "observer": 0,
                        "attempt": attempt_number,
                        "event_context": event_context,
                        "training_sample": sample_number,
                        "training_sample_limit": (
                            sample_limit
                        ),
                        "captured_at_utc": datetime.now(UTC).isoformat(),
                        "source_image_kind": (
                            "original_html"
                            if sample_path != captured_path
                            else "screenshot"
                        ),
                        "detection_origin": detection_origin,
                        "portal_stage": "reservation_captcha_training_sample",
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Could not enqueue reservation CAPTCHA training sample %s: %s",
                    sample_number,
                    exc,
                )
                enqueued = False
            if enqueued:
                shadow_event_ids.append(event_id)
            else:
                logger.warning(
                    "Reservation CAPTCHA training sample was not enqueued: %s",
                    event_id,
                )

        refresh_started = time.monotonic()
        refreshed = refresh_reservation_captcha(page, settings)
        refresh_duration_ms = round(
            max(time.monotonic() - refresh_started, 0.0) * 1000,
            3,
        )
        sample_timings.append(
            {
                "sample": sample_number,
                "capture_duration_ms": capture_duration_ms,
                "refresh_duration_ms": refresh_duration_ms,
                "total_duration_ms": round(
                    max(time.monotonic() - sample_started, 0.0) * 1000,
                    3,
                ),
                "refreshed": refreshed,
            }
        )
        if not refreshed:
            logger.warning(
                "Could not refresh reservation CAPTCHA after training sample %s; "
                "continuing with the current CAPTCHA",
                sample_number,
            )
            break

    captcha_audit["captcha_training_sample_limit"] = sample_limit
    captcha_audit["captcha_training_sample_paths"] = sample_paths
    captcha_audit["captcha_training_samples_collected"] = len(sample_paths)
    captcha_audit["captcha_training_sample_timings"] = sample_timings
    captcha_audit["captcha_training_shadow_event_ids"] = shadow_event_ids
    captcha_audit["captcha_training_duration_ms"] = round(
        max(time.monotonic() - started, 0.0) * 1000,
        3,
    )
    logger.info(
        "Collected %s of %s extra reservation CAPTCHA samples in %s ms",
        len(sample_paths),
        extra_sample_count,
        captcha_audit["captcha_training_duration_ms"],
    )


def _resolve_sample_limit(
    settings: Settings,
    captcha_authority: CaptchaAuthority | None,
) -> int:
    if not settings.reservation_captcha_runtime_control_enabled:
        return 1
    try:
        if captcha_authority is None:
            raise RuntimeError("CaptchaAuthority is not configured.")
        return captcha_authority.sample_limit(settings)
    except Exception as exc:
        logger.warning(
            "Could not read runtime CAPTCHA sampling control; using configured fallback: %s",
            exc,
        )
        return settings.reservation_captcha_sample_limit


def _ensure_reservation_can_continue(
    cancel_event: threading.Event | None,
    can_submit: Callable[[], bool] | None,
) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico durante la captura de CAPTCHA para entrenamiento."
        )
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled(
            "La orden fue pausada durante la captura de CAPTCHA para entrenamiento."
        )
