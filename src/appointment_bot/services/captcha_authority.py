from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from appointment_bot.config import Settings
from appointment_bot.db.captcha_authority import (
    get_captcha_authority_control,
    record_captcha_authority_decision,
    trip_captcha_authority_circuit,
)
from appointment_bot.services.captcha import solve_normal_captcha

logger = logging.getLogger(__name__)

V6_MODEL_NAME = "v6_sequence_candidate"
CAPTCHA_ANSWER_PATTERN = re.compile(r"[A-Z0-9]{5}")


@dataclass(frozen=True)
class CaptchaAuthorityResult:
    answer: str
    source: str
    decision_id: str | None
    fallback_reason: str | None
    local_request_ms: float | None = None
    local_inference_ms: float | None = None
    mean_confidence: float | None = None
    min_char_confidence: float | None = None
    sequence_confidence_product: float | None = None


def solve_reservation_captcha(
    image_path: Path,
    settings: Settings,
    *,
    event_id: str | None,
    run_id: str | None,
    order_id: str | None,
    attempt_number: int,
    metadata: dict[str, Any] | None,
    fallback_solver: Callable[[Path, Settings], str] = solve_normal_captcha,
) -> CaptchaAuthorityResult:
    control = get_captcha_authority_control(settings)
    if control.mode != "canary" or event_id is None:
        return CaptchaAuthorityResult(
            answer=fallback_solver(image_path, settings),
            source="2captcha",
            decision_id=None,
            fallback_reason="mode_2captcha" if control.mode != "canary" else "missing_event_id",
        )

    if not control.local_admission_open:
        reason = (
            "circuit_open"
            if control.circuit_state == "open"
            else "canary_limit_reached"
        )
        decision = record_captcha_authority_decision(
            event_id=event_id,
            run_id=run_id,
            order_id=order_id,
            attempt_number=attempt_number,
            prediction=None,
            mean_confidence=None,
            min_char_confidence=None,
            sequence_confidence_product=None,
            inference_ms=None,
            request_ms=None,
            fallback_reason=reason,
            settings=settings,
        )
        return _solve_with_fallback(
            image_path,
            settings,
            decision_id=decision.decision_id,
            fallback_reason=decision.fallback_reason,
            fallback_solver=fallback_solver,
        )

    try:
        prediction = _predict_v6(
            image_path,
            settings,
            event_id=event_id,
            metadata=metadata or {},
            timeout_ms=control.timeout_ms,
        )
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        reason = _local_failure_reason(exc)
        logger.warning(
            "captcha_authority_local_failure event_id=%s reason=%s error=%s",
            event_id,
            reason,
            exc,
        )
        trip_captcha_authority_circuit(reason, settings=settings)
        decision = record_captcha_authority_decision(
            event_id=event_id,
            run_id=run_id,
            order_id=order_id,
            attempt_number=attempt_number,
            prediction=None,
            mean_confidence=None,
            min_char_confidence=None,
            sequence_confidence_product=None,
            inference_ms=None,
            request_ms=None,
            fallback_reason=reason,
            settings=settings,
        )
        return _solve_with_fallback(
            image_path,
            settings,
            decision_id=decision.decision_id,
            fallback_reason=decision.fallback_reason,
            fallback_solver=fallback_solver,
        )

    decision = record_captcha_authority_decision(
        event_id=event_id,
        run_id=run_id,
        order_id=order_id,
        attempt_number=attempt_number,
        prediction=prediction.answer,
        mean_confidence=prediction.mean_confidence,
        min_char_confidence=prediction.min_char_confidence,
        sequence_confidence_product=prediction.sequence_confidence_product,
        inference_ms=prediction.local_inference_ms,
        request_ms=prediction.local_request_ms,
        fallback_reason=None,
        settings=settings,
    )
    if decision.source != "v6":
        return _solve_with_fallback(
            image_path,
            settings,
            decision_id=decision.decision_id,
            fallback_reason=decision.fallback_reason,
            prediction=prediction,
            fallback_solver=fallback_solver,
        )
    logger.info(
        "captcha_authority_v6_selected event_id=%s decision_id=%s request_ms=%.3f",
        event_id,
        decision.decision_id,
        prediction.local_request_ms,
    )
    return CaptchaAuthorityResult(
        answer=prediction.answer,
        source="v6",
        decision_id=decision.decision_id,
        fallback_reason=None,
        local_request_ms=prediction.local_request_ms,
        local_inference_ms=prediction.local_inference_ms,
        mean_confidence=prediction.mean_confidence,
        min_char_confidence=prediction.min_char_confidence,
        sequence_confidence_product=prediction.sequence_confidence_product,
    )


def _solve_with_fallback(
    image_path: Path,
    settings: Settings,
    *,
    decision_id: str,
    fallback_reason: str | None,
    prediction: CaptchaAuthorityResult | None = None,
    fallback_solver: Callable[[Path, Settings], str] = solve_normal_captcha,
) -> CaptchaAuthorityResult:
    return CaptchaAuthorityResult(
        answer=fallback_solver(image_path, settings),
        source="2captcha",
        decision_id=decision_id,
        fallback_reason=fallback_reason,
        local_request_ms=prediction.local_request_ms if prediction else None,
        local_inference_ms=prediction.local_inference_ms if prediction else None,
        mean_confidence=prediction.mean_confidence if prediction else None,
        min_char_confidence=prediction.min_char_confidence if prediction else None,
        sequence_confidence_product=(
            prediction.sequence_confidence_product if prediction else None
        ),
    )


def _predict_v6(
    image_path: Path,
    settings: Settings,
    *,
    event_id: str,
    metadata: dict[str, Any],
    timeout_ms: int,
) -> CaptchaAuthorityResult:
    payload = json.dumps(
        {
            "event_id": event_id,
            "image_path": str(image_path.resolve()),
            "metadata": metadata,
        }
    ).encode("utf-8")
    request = Request(
        f"{settings.captcha_shadow_url.rstrip('/')}/v1/predict",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    with urlopen(request, timeout=timeout_ms / 1000) as response:
        result = json.loads(response.read().decode("utf-8"))
    request_ms = round(max(time.monotonic() - started, 0.0) * 1000, 3)
    event = result.get("event")
    if not isinstance(event, dict):
        raise ValueError("local_response_missing_event")
    predictions = event.get("predictions")
    if not isinstance(predictions, list):
        raise ValueError("local_response_missing_predictions")
    selected = next(
        (
            item
            for item in predictions
            if isinstance(item, dict) and item.get("model_name") == V6_MODEL_NAME
        ),
        None,
    )
    if selected is None:
        raise ValueError("v6_prediction_missing")
    answer = str(selected.get("prediction") or "").strip().upper()
    if CAPTCHA_ANSWER_PATTERN.fullmatch(answer) is None:
        raise ValueError("v6_prediction_invalid_format")
    return CaptchaAuthorityResult(
        answer=answer,
        source="v6",
        decision_id=None,
        fallback_reason=None,
        local_request_ms=request_ms,
        local_inference_ms=_required_float(selected, "inference_ms"),
        mean_confidence=_required_confidence(selected, "mean_confidence"),
        min_char_confidence=_required_confidence(selected, "min_char_confidence"),
        sequence_confidence_product=_required_confidence(
            selected, "sequence_confidence_product"
        ),
    )


def _required_float(payload: dict[str, Any], field: str) -> float:
    value = payload.get(field)
    if isinstance(value, bool):
        raise ValueError(f"v6_{field}_invalid")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"v6_{field}_invalid") from exc
    if number < 0:
        raise ValueError(f"v6_{field}_invalid")
    return number


def _required_confidence(payload: dict[str, Any], field: str) -> float:
    number = _required_float(payload, field)
    if number > 1:
        raise ValueError(f"v6_{field}_invalid")
    return number


def _local_failure_reason(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"local_http_{exc.code}"
    if isinstance(exc, (TimeoutError, URLError)):
        return "local_unavailable_or_timeout"
    message = str(exc).strip().lower()
    if message.startswith("v6_") or message.startswith("local_response_"):
        return message[:120]
    return "local_solver_failure"
