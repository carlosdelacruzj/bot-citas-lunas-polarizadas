from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings, load_settings
from appointment_bot.db.hosted_registrations import update_registration_after_preflight
from appointment_bot.db.orders import (
    get_service_order_runtime,
    list_service_order_summaries,
    mark_order_preflight_failed,
    mark_order_preflight_pending,
    mark_order_preflight_running,
    mark_order_preflight_validated,
    record_order_program_listing,
)
from appointment_bot.reports.run_reporting import settings_for_order
from appointment_bot.reservation_engine.appointments import read_person_name
from appointment_bot.reservation_engine.login import InvalidPortalCredentials, login
from appointment_bot.reservation_engine.programs import read_program_action_rows
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_ORDERS: set[str] = set()


def resume_pending_order_preflights(*, settings: Settings | None = None) -> int:
    settings = settings or load_settings(require_login=False)
    order_ids = [
        order.order_id
        for order in list_service_order_summaries(settings)
        if order.preflight_status in {"pending", "running"}
    ]
    return sum(schedule_order_preflight(order_id, settings=settings) for order_id in order_ids)


def schedule_order_preflight(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> bool:
    settings = settings or load_settings(require_login=False)
    with _ACTIVE_LOCK:
        if order_id in _ACTIVE_ORDERS:
            return False
        _ACTIVE_ORDERS.add(order_id)
    mark_order_preflight_pending(order_id, settings=settings)
    thread = threading.Thread(
        target=_run_scheduled_preflight,
        args=(order_id, settings),
        name=f"order-preflight-{order_id}",
        daemon=True,
    )
    thread.start()
    return True


def validate_order_preflight(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, object]:
    settings = settings or load_settings(require_login=False)
    mark_order_preflight_running(order_id, settings=settings)
    order = get_service_order_runtime(order_id, settings=settings)
    if order is None:
        raise ValueError(f"Service order not found: {order_id}")
    order_settings = settings_for_order(
        settings,
        username=order.username,
        password=order.password,
        document_type=order.document_type,
    )
    with open_page(order_settings, headless=True) as page:
        try:
            login(page, order_settings)
            applicant_name = _read_portal_applicant_name(page)
            if not applicant_name or _looks_like_document(applicant_name, order.username):
                raise RuntimeError("El portal no mostro un nombre completo verificable.")
            rows = read_program_action_rows(page)
            pending_rows = [
                row
                for row in rows
                if str(row.get("status") or "").strip().casefold() == "pendiente"
            ]
            listing = {
                "program_count": len(rows),
                "pending_count": len(pending_rows),
                "rows": rows,
                "source": "registration_preflight",
            }
            record_order_program_listing(order_id, listing, settings=settings)
            if not pending_rows:
                raise RuntimeError(
                    "El acceso funciona, pero no se encontro ningun tramite "
                    "PENDIENTE para reservar."
                )
            details = {
                "applicant_name": applicant_name,
                "document_type": order.document_type,
                "program_count": len(rows),
                "pending_count": len(pending_rows),
                "programs": pending_rows[:10],
            }
            mark_order_preflight_validated(
                order_id,
                applicant_name=applicant_name,
                details=details,
                settings=settings,
            )
            _sync_hosted_preflight_state(
                order_id,
                state="accepted",
                settings=settings,
            )
            logger.info(
                "Order preflight validated: order=%s programs=%s pending=%s",
                order_id,
                len(rows),
                len(pending_rows),
            )
            return {"status": "validated", **details}
        except InvalidPortalCredentials as exc:
            _save_failure_screenshot(page, order_id, order_settings.screenshots_dir)
            return _fail_preflight(order_id, str(exc), "invalid_credentials", settings)
        except Exception as exc:
            _save_failure_screenshot(page, order_id, order_settings.screenshots_dir)
            return _fail_preflight(order_id, str(exc), exc.__class__.__name__, settings)


def _run_scheduled_preflight(order_id: str, settings: Settings) -> None:
    try:
        validate_order_preflight(order_id, settings=settings)
    except Exception as exc:
        logger.exception("Unexpected order preflight failure for %s", order_id)
        try:
            _fail_preflight(order_id, str(exc), exc.__class__.__name__, settings)
        except Exception:
            logger.exception("Could not persist unexpected preflight failure for %s", order_id)
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_ORDERS.discard(order_id)


def _read_portal_applicant_name(page) -> str:
    direct_name = " ".join(read_person_name(page).split())
    if direct_name:
        return direct_name
    body_text = page.locator("body").inner_text(timeout=5_000)
    match = re.search(
        r"Sistema de Lunas Oscurecidas\s+(.+?)\s+listado de Solicitudes",
        body_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return " ".join(match.group(1).split()) if match else ""


def _looks_like_document(name: str, document_number: str) -> bool:
    normalized_name = "".join(character for character in name if character.isalnum()).casefold()
    normalized_document = "".join(
        character for character in document_number if character.isalnum()
    ).casefold()
    return normalized_name == normalized_document or not any(
        character.isalpha() for character in name
    )


def _fail_preflight(
    order_id: str,
    message: str,
    error_type: str,
    settings: Settings,
) -> dict[str, object]:
    safe_message = sanitize_text(message) or "No se pudo validar la cuenta en el portal."
    details = {"error_type": error_type}
    mark_order_preflight_failed(
        order_id,
        safe_message,
        details=details,
        settings=settings,
    )
    _sync_hosted_preflight_state(
        order_id,
        state="credentials_invalid" if error_type == "invalid_credentials" else "retry_wait",
        error_category=error_type,
        settings=settings,
    )
    logger.warning("Order preflight failed: order=%s error=%s", order_id, safe_message)
    return {"status": "failed", "message": safe_message, **details}


def _sync_hosted_preflight_state(
    order_id: str,
    *,
    state: str,
    settings: Settings,
    error_category: str | None = None,
) -> None:
    try:
        update_registration_after_preflight(
            order_id,
            state=state,
            error_category=error_category,
            settings=settings,
        )
    except Exception:
        logger.exception("Could not synchronize hosted registration for %s", order_id)


def _save_failure_screenshot(page, order_id: str, screenshots_dir: Path) -> None:
    try:
        directory = screenshots_dir / "preflight"
        directory.mkdir(parents=True, exist_ok=True)
        safe_order = re.sub(r"[^A-Za-z0-9_.-]", "-", order_id)
        page.screenshot(path=str(directory / f"preflight-error-{safe_order}.png"), full_page=True)
    except Exception:
        logger.exception("Could not save preflight failure screenshot for %s", order_id)
