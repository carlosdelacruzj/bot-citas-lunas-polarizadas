from __future__ import annotations

import logging
import threading
from dataclasses import replace
from pathlib import Path

from appointment_bot.browser.session import open_page
from appointment_bot.config import Settings
from appointment_bot.db.orders import get_service_order_runtime
from appointment_bot.db.reservations import replace_confirmed_reservation_evidence
from appointment_bot.domain import RunReport
from appointment_bot.reports.run_reporting import settings_for_order
from appointment_bot.reservation_engine.login import login
from appointment_bot.reservation_engine.programs import click_program_action
from appointment_bot.reservation_engine.stages import read_process_stages
from appointment_bot.utils.screenshots import (
    save_error_screenshot,
    save_programmed_review_screenshot,
)

logger = logging.getLogger(__name__)


def review_confirmed_orders_after_queue(
    settings: Settings,
    order_ids: list[str],
    *,
    cancel_event: threading.Event | None = None,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for order_id in dict.fromkeys(order_ids):
        if cancel_event is not None and cancel_event.is_set():
            results.append(
                {
                    "order_id": order_id,
                    "status": "skipped",
                    "message": "Revision cancelada por pausa del worker.",
                }
            )
            break
        results.append(_review_confirmed_order(settings, order_id))
    return results


def replace_reports_with_reviewed_evidence(
    reports: list[RunReport],
    review_results: list[dict[str, str]],
) -> list[RunReport]:
    reviewed_paths = {
        result["order_id"]: result["screenshot_path"]
        for result in review_results
        if result.get("status") == "completed"
        and result.get("order_id")
        and result.get("screenshot_path")
        and Path(result["screenshot_path"]).is_file()
    }
    return [
        replace(
            report,
            screenshot_path=reviewed_paths[report.order_id],
            screenshot_paths=[reviewed_paths[report.order_id]],
        )
        if report.order_id in reviewed_paths
        else report
        for report in reports
    ]


def _review_confirmed_order(settings: Settings, order_id: str) -> dict[str, str]:
    order = get_service_order_runtime(order_id, settings=settings)
    if order is None:
        return {
            "order_id": order_id,
            "status": "error",
            "message": "La orden ya no existe.",
        }
    review_settings = replace(
        settings_for_order(settings, username=order.username, password=order.password),
        headless=True,
        block_heavy_assets=False,
        monitor_window_seconds=0,
        telegram_notify_unavailable=False,
        artifact_prefix=f"postreview-{order_id}",
    )
    try:
        with open_page(
            review_settings,
            headless=True,
            block_heavy_assets=False,
        ) as page:
            try:
                login(page, review_settings)
                page = click_program_action(
                    page,
                    program_expediente=order.program_expediente,
                    program_plate=order.program_plate,
                )
                stages = read_process_stages(page)
                programmed = next(
                    (
                        stage
                        for stage in stages
                        if stage.stage.strip().casefold() == "separa cita peritaje"
                        and stage.status.strip().casefold() == "programado"
                    ),
                    None,
                )
                if programmed is None:
                    raise RuntimeError(
                        "La revision no encontro Separa Cita Peritaje en Programado."
                    )
                screenshot = save_programmed_review_screenshot(page, review_settings)
                if screenshot is None:
                    raise RuntimeError(
                        "No se pudo capturar la region nitida de nombres y etapas."
                    )
                stable = replace_confirmed_reservation_evidence(
                    order_id,
                    screenshot,
                    settings=review_settings,
                )
                logger.info(
                    "Post-queue reservation review completed: order_id=%s evidence=%s",
                    order_id,
                    stable,
                )
                return {
                    "order_id": order_id,
                    "status": "completed",
                    "message": "Programado verificado y evidencia actualizada.",
                    "screenshot_path": str(screenshot),
                    "evidence_path": str(stable),
                }
            except Exception:
                save_error_screenshot(page, review_settings, label="post-queue-review-error")
                raise
    except Exception as exc:
        logger.exception("Post-queue reservation review failed: order_id=%s", order_id)
        return {
            "order_id": order_id,
            "status": "error",
            "message": str(exc),
        }


__all__ = [
    "replace_reports_with_reviewed_evidence",
    "review_confirmed_orders_after_queue",
]
