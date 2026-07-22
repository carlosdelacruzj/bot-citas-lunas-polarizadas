from __future__ import annotations

import json
import logging
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from appointment_bot.config import Settings, load_settings
from appointment_bot.db.captcha_shadow_outbox import (
    captcha_shadow_external_timing_stats,
    captcha_shadow_external_timings,
    captcha_shadow_outbox_status,
)
from appointment_bot.services.api.captcha_shadow_quality import (
    ALLOWED_CASE_TYPES,
    build_captcha_dataset_zip,
    build_captcha_quality,
    build_captcha_quality_cases,
)
from appointment_bot.services.api.http import error_payload

logger = logging.getLogger(__name__)

ALLOWED_PAGE_SIZES = {12, 24, 48}
ALLOWED_AGREEMENTS = {"all", "match", "mismatch", "pending"}
ALLOWED_PORTAL_STATUSES = {"all", "accepted", "rejected", "unverified"}
ALLOWED_SOURCES = {"all", "reservation", "observer"}
ALLOWED_REVIEW_STATUSES = {"all", "validated", "pending"}
ALLOWED_SORTS = {"newest", "oldest", "review_priority"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
QUALITY_CASE_PAGE_SIZES = {12, 24, 48}


def captcha_shadow_summary_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    settings = load_settings(require_login=False)
    try:
        health = _shadow_get(settings, "/health")
        stats = _shadow_get(settings, "/v1/stats")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("captcha_shadow_dashboard_summary_failed error=%s", exc)
        return HTTPStatus.SERVICE_UNAVAILABLE, error_payload(
            "captcha_shadow_unavailable",
            "El servicio local de CAPTCHA no está disponible.",
        )
    try:
        outbox = captcha_shadow_outbox_status(settings=settings)
    except Exception:
        logger.exception("captcha_shadow_dashboard_outbox_status_failed")
        outbox = {"pending": 0, "processed": 0, "attempts": 0}
    return HTTPStatus.OK, {
        "status": str(health.get("status") or "unknown"),
        "device": health.get("device"),
        "models": list(health.get("models") or []),
        "started_at_utc": health.get("started_at_utc"),
        "stats": stats,
        "outbox": outbox,
    }


def captcha_shadow_events_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        page = max(1, int(_query_value(query, "page", "1")))
        page_size = int(_query_value(query, "page_size", "12"))
    except ValueError:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "Página o tamaño de página inválido."
        )
    if page_size not in ALLOWED_PAGE_SIZES:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "El tamaño de página debe ser 12, 24 o 48."
        )
    agreement = _query_value(query, "agreement", "all")
    portal_status = _query_value(query, "portal_status", "all")
    source = _query_value(query, "source", "all")
    review_status = _query_value(query, "review_status", "all")
    sort = _query_value(query, "sort", "newest")
    if (
        agreement not in ALLOWED_AGREEMENTS
        or portal_status not in ALLOWED_PORTAL_STATUSES
        or source not in ALLOWED_SOURCES
        or review_status not in ALLOWED_REVIEW_STATUSES
        or sort not in ALLOWED_SORTS
    ):
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "Los filtros de CAPTCHA no son válidos."
        )
    search = _query_value(query, "q", "").strip()[:100]
    offset = (page - 1) * page_size
    settings = load_settings(require_login=False)
    shadow_query = urlencode(
        {
            "limit": page_size,
            "offset": offset,
            "q": search,
            "agreement": agreement,
            "portal_status": portal_status,
            "source": source,
            "review_status": review_status,
            "sort": sort,
        }
    )
    try:
        response = _shadow_get(settings, f"/v1/events?{shadow_query}")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("captcha_shadow_dashboard_events_failed error=%s", exc)
        return HTTPStatus.SERVICE_UNAVAILABLE, error_payload(
            "captcha_shadow_unavailable",
            "No se pudieron cargar los eventos del servicio local de CAPTCHA.",
        )
    raw_events = response.get("events")
    if not isinstance(raw_events, list):
        return HTTPStatus.BAD_GATEWAY, error_payload(
            "captcha_shadow_invalid_response",
            "El servicio local devolvió una respuesta inesperada.",
        )
    event_ids = [
        str(event.get("event_id"))
        for event in raw_events
        if isinstance(event, dict) and event.get("event_id")
    ]
    try:
        external_timings = captcha_shadow_external_timings(event_ids, settings=settings)
    except Exception:
        logger.exception("captcha_shadow_dashboard_timings_failed")
        external_timings = {}
    events = [
        _sanitize_event(event, external_timings)
        for event in raw_events
        if isinstance(event, dict)
    ]
    total = max(0, int(response.get("total", len(events))))
    total_pages = max(1, (total + page_size - 1) // page_size)
    return HTTPStatus.OK, {
        "events": events,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
        "filters": {
            "q": search,
            "agreement": agreement,
            "portal_status": portal_status,
            "source": source,
            "review_status": review_status,
            "sort": sort,
        },
    }


def captcha_shadow_quality_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    settings = load_settings(require_login=False)
    try:
        events = _shadow_all_events(settings)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("captcha_shadow_quality_failed error=%s", exc)
        return HTTPStatus.SERVICE_UNAVAILABLE, error_payload(
            "captcha_shadow_unavailable",
            "No se pudo calcular la calidad de los modelos CAPTCHA.",
        )
    event_ids = [str(event.get("event_id") or "") for event in events]
    try:
        external_stats = captcha_shadow_external_timing_stats(
            [event_id for event_id in event_ids if event_id],
            settings=settings,
        )
    except Exception:
        logger.exception("captcha_shadow_quality_external_timings_failed")
        external_stats = {"samples": 0, "average": None, "p50": None, "p90": None}
    return HTTPStatus.OK, build_captcha_quality(events, external_stats)


def captcha_shadow_quality_cases_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    case_type = _query_value(query, "type", "wrong")
    try:
        page = max(1, int(_query_value(query, "page", "1")))
        page_size = int(_query_value(query, "page_size", "12"))
    except ValueError:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "Página o tamaño de página inválido."
        )
    if case_type not in ALLOWED_CASE_TYPES or page_size not in QUALITY_CASE_PAGE_SIZES:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "El tipo de caso o tamaño de página no es válido."
        )
    settings = load_settings(require_login=False)
    try:
        raw_events = _shadow_all_events(settings)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("captcha_shadow_quality_cases_failed error=%s", exc)
        return HTTPStatus.SERVICE_UNAVAILABLE, error_payload(
            "captcha_shadow_unavailable",
            "No se pudieron cargar los casos de calidad CAPTCHA.",
        )
    cases = [
        case
        for case in build_captcha_quality_cases(raw_events)
        if case_type in case["case_types"]
    ]
    total = len(cases)
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * page_size
    page_cases = cases[offset : offset + page_size]
    event_ids = [str(case.get("event_id") or "") for case in page_cases]
    try:
        external_timings = captcha_shadow_external_timings(event_ids, settings=settings)
    except Exception:
        logger.exception("captcha_shadow_quality_case_timings_failed")
        external_timings = {}
    for case in page_cases:
        event_id = str(case.get("event_id") or "")
        case["external_solve_ms"] = external_timings.get(event_id)
        case["image_url"] = (
            f"/api/v1/captcha-shadow/events/{quote(event_id, safe='')}/image"
        )
    return HTTPStatus.OK, {
        "cases": page_cases,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
        "filters": {"type": case_type},
    }


def captcha_shadow_dataset_export_payload() -> tuple[HTTPStatus, bytes | dict[str, Any]]:
    settings = load_settings(require_login=False)
    try:
        events = _shadow_all_events(settings)
        archive, _ = build_captcha_dataset_zip(events, settings.screenshots_dir)
    except ValueError as exc:
        return HTTPStatus.CONFLICT, error_payload(
            "captcha_dataset_unavailable",
            str(exc),
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("captcha_shadow_dataset_export_failed error=%s", exc)
        return HTTPStatus.SERVICE_UNAVAILABLE, error_payload(
            "captcha_shadow_unavailable",
            "No se pudo preparar el dataset de CAPTCHA.",
        )
    return HTTPStatus.OK, archive


def captcha_shadow_human_label_event_id(path: str) -> str | None:
    prefix = "/api/v1/captcha-shadow/events/"
    suffix = "/human-label"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    value = path[len(prefix) : -len(suffix)]
    return unquote(value) if value else None


def save_captcha_shadow_human_label_payload(
    event_id: str,
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    answer = str(payload.get("answer") or "").strip().upper()
    image_sha256 = str(payload.get("expected_image_sha256") or "").strip().lower()
    note = str(payload.get("note") or "").strip()
    allowed_answer_characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    if len(answer) != 5 or any(char not in allowed_answer_characters for char in answer):
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "La respuesta debe tener exactamente cinco letras o números."
        )
    if len(image_sha256) != 64 or any(char not in "0123456789abcdef" for char in image_sha256):
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request", "La imagen cambió; actualiza la vista antes de validar."
        )
    settings = load_settings(require_login=False)
    try:
        response = _shadow_post(
            settings,
            f"/v1/events/{quote(event_id, safe='')}/human-label",
            {
                "answer": answer,
                "expected_image_sha256": image_sha256,
                "reviewer": "dashboard-owner",
                "note": note[:500],
            },
        )
    except HTTPError as exc:
        if exc.code == HTTPStatus.NOT_FOUND:
            return HTTPStatus.NOT_FOUND, error_payload(
                "not_found", "No se encontró el evento CAPTCHA."
            )
        return HTTPStatus.BAD_REQUEST, error_payload(
            "captcha_label_rejected", "No se pudo guardar la validación del CAPTCHA."
        )
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("captcha_shadow_human_label_failed event_id=%s error=%s", event_id, exc)
        return HTTPStatus.SERVICE_UNAVAILABLE, error_payload(
            "captcha_shadow_unavailable",
            "El servicio local no pudo guardar la validación.",
        )
    event = response.get("event")
    if not isinstance(event, dict):
        return HTTPStatus.BAD_GATEWAY, error_payload(
            "captcha_shadow_invalid_response",
            "El servicio local devolvió una respuesta inesperada.",
        )
    return HTTPStatus.OK, {"event": _sanitize_event(event, {})}


def captcha_shadow_image_payload(
    event_id: str,
) -> tuple[HTTPStatus, Path | dict[str, Any]]:
    settings = load_settings(require_login=False)
    try:
        response = _shadow_get(settings, f"/v1/events/{quote(event_id, safe='')}")
    except HTTPError as exc:
        if exc.code == HTTPStatus.NOT_FOUND:
            return HTTPStatus.NOT_FOUND, error_payload(
                "not_found", "No se encontró el evento CAPTCHA."
            )
        return HTTPStatus.BAD_GATEWAY, error_payload(
            "captcha_shadow_unavailable", "No se pudo consultar el evento CAPTCHA."
        )
    except (URLError, TimeoutError, OSError, ValueError):
        return HTTPStatus.SERVICE_UNAVAILABLE, error_payload(
            "captcha_shadow_unavailable", "El servicio local de CAPTCHA no está disponible."
        )
    event = response.get("event")
    image_value = event.get("image_path") if isinstance(event, dict) else None
    if not isinstance(image_value, str) or not image_value:
        return HTTPStatus.NOT_FOUND, error_payload(
            "not_found", "El evento no tiene una imagen disponible."
        )
    image_path = Path(image_value).resolve()
    screenshots_root = settings.screenshots_dir.resolve()
    if not image_path.is_relative_to(screenshots_root):
        logger.warning("captcha_shadow_image_outside_root event_id=%s", event_id)
        return HTTPStatus.FORBIDDEN, error_payload(
            "forbidden", "La imagen no pertenece al directorio autorizado."
        )
    if not image_path.is_file():
        return HTTPStatus.NOT_FOUND, error_payload(
            "not_found", "La imagen CAPTCHA ya no está disponible."
        )
    return HTTPStatus.OK, image_path


def captcha_shadow_image_event_id(path: str) -> str | None:
    prefix = "/api/v1/captcha-shadow/events/"
    suffix = "/image"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    value = path[len(prefix) : -len(suffix)]
    return unquote(value) if value else None


def _shadow_all_events(settings: Settings) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = urlencode(
            {
                "limit": 100,
                "offset": offset,
                "agreement": "all",
                "portal_status": "all",
                "source": "all",
                "review_status": "all",
                "sort": "oldest",
            }
        )
        response = _shadow_get(settings, f"/v1/events?{query}")
        page = response.get("events")
        if not isinstance(page, list):
            raise ValueError("Invalid CAPTCHA shadow events response")
        valid_page = [event for event in page if isinstance(event, dict)]
        events.extend(valid_page)
        total = max(0, int(response.get("total", len(events))))
        if not page or len(events) >= total:
            return events
        offset += len(page)
        if offset > 100_000:
            raise ValueError("CAPTCHA shadow event limit exceeded")


def _shadow_get(settings: Settings, path: str) -> dict[str, Any]:
    base_url = settings.captcha_shadow_url.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("CAPTCHA_SHADOW_URL must use a local HTTP address")
    request = Request(f"{base_url}{path}", method="GET")
    with urlopen(request, timeout=settings.captcha_shadow_timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid CAPTCHA shadow response")
    return payload


def _shadow_post(settings: Settings, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = settings.captcha_shadow_url.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("CAPTCHA_SHADOW_URL must use a local HTTP address")
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=settings.captcha_shadow_timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(response_payload, dict):
        raise ValueError("Invalid CAPTCHA shadow response")
    return response_payload


def _sanitize_event(
    event: dict[str, Any],
    external_timings: dict[str, float],
) -> dict[str, Any]:
    event_id = str(event.get("event_id") or "")
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    predictions = []
    for prediction in event.get("predictions") or []:
        if not isinstance(prediction, dict):
            continue
        predictions.append(
            {
                key: prediction.get(key)
                for key in (
                    "model_name",
                    "prediction",
                    "mean_confidence",
                    "min_char_confidence",
                    "sequence_confidence_product",
                    "char_confidences",
                    "inference_ms",
                    "created_at_utc",
                )
            }
        )
    selected = next(
        (item for item in predictions if item.get("model_name") == "v2_selected"),
        None,
    )
    external_answer = event.get("external_answer")
    return {
        "event_id": event_id,
        "image_sha256": event.get("image_sha256"),
        "received_at_utc": event.get("received_at_utc"),
        "external_answer": external_answer,
        "external_solve_ms": external_timings.get(event_id),
        "portal_accepted": event.get("portal_accepted"),
        "human_label": event.get("human_label"),
        "metadata": {
            key: metadata.get(key)
            for key in (
                "run_id",
                "order_id",
                "attempt",
                "captured_at_utc",
                "source_image_kind",
                "detection_origin",
                "backfilled",
                "observer",
                "portal_stage",
            )
        },
        "predictions": predictions,
        "selected_matches_external": bool(
            selected
            and external_answer
            and selected.get("prediction") == external_answer
        ),
        "image_url": (
            f"/api/v1/captcha-shadow/events/{quote(event_id, safe='')}/image"
        ),
    }


def _query_value(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    return values[0] if values else default
