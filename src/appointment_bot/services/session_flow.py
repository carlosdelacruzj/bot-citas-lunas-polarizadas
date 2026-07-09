from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult
from appointment_bot.flows.appointments import open_appointment_panel
from appointment_bot.flows.login import login
from appointment_bot.flows.programs import click_program_action
from appointment_bot.flows.stages import appointment_stage_result, read_process_stages
from appointment_bot.services.notifier import notify_result
from appointment_bot.services.session_monitor import monitor_appointment_availability
from appointment_bot.services.session_programs import notify_multiple_programs
from appointment_bot.services.session_results import with_client_context
from appointment_bot.utils.screenshots import save_screenshot

logger = logging.getLogger(__name__)


@dataclass
class SessionFlowResult:
    final_result: AvailabilityResult
    screenshot_path: Path | None
    screenshot_paths: list[Path]


def execute_session_flow(
    page,
    settings: Settings,
    *,
    order_id: str | None = None,
    client_name: str | None = None,
    cancel_event: threading.Event | None = None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None = None,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[dict | None], None] | None = None,
    on_submission_started: Callable[[dict | None], None] | None = None,
    expected_person_name: str | None = None,
    notify_mode: str = "full",
) -> SessionFlowResult:
    login(page, settings)
    page = click_program_action(
        page,
        on_multiple_programs=lambda details: notify_multiple_programs(
            settings,
            order_id,
            client_name,
            details,
        ),
    )
    stages = read_process_stages(page)
    stage_result = appointment_stage_result(stages)
    if stage_result is not None:
        stage_result = with_client_context(
            stage_result,
            order_id=order_id,
            client_name=client_name,
            settings=settings,
        )
        screenshot_path = save_process_stages_snapshot(page, settings)
        if notify_mode == "full":
            notify_result(stage_result, settings, screenshot_path)
        logger.info("Finished appointment check: %s", stage_result.status)
        return SessionFlowResult(stage_result, screenshot_path, [])

    page = open_appointment_panel(page)
    result, screenshot_path, screenshot_paths = monitor_appointment_availability(
        page,
        settings,
        None,
        cancel_event,
        on_check,
        is_allowed_appointment,
        can_submit,
        can_solve_captcha,
        on_submission_intent,
        on_submission_started,
        expected_person_name,
    )
    result = with_client_context(
        result,
        order_id=order_id,
        client_name=client_name,
        settings=settings,
    )
    if notify_mode == "full":
        notify_result(
            result,
            settings,
            screenshot_path,
            screenshot_paths=screenshot_paths,
        )
    logger.info("Finished appointment check: %s", result.status)
    return SessionFlowResult(result, screenshot_path, screenshot_paths)


def save_process_stages_snapshot(
    page,
    settings: Settings,
    *,
    label: str = "02-detalle-tramite-etapas-reservar-cita",
) -> Path | None:
    return save_screenshot(page, settings, label=label)
