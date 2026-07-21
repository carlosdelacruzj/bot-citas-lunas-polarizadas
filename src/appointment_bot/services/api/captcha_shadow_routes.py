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
    captcha_shadow_external_timings,
    captcha_shadow_outbox_status,
)
from appointment_bot.services.api.http import error_payload

logger = logging.getLogger(__name__)

ALLOWED_PAGE_SIZES = {12, 24, 48}
ALLOWED_AGREEMENTS = {"all", "match", "mismatch", "pending"}
ALLOWED_PORTAL_STATUSES = {"all", "accepted", "rejected", "unverified"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


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
    if agreement not in ALLOWED_AGREEMENTS or portal_status not in ALLOWED_PORTAL_STATUSES:
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
        },
    }


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
        "received_at_utc": event.get("received_at_utc"),
        "external_answer": external_answer,
        "external_solve_ms": external_timings.get(event_id),
        "portal_accepted": event.get("portal_accepted"),
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
