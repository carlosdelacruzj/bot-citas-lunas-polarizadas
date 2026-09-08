from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from appointment_bot.configuration.captcha import CaptchaSettings
from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.configuration.reservation import ReservationSettings
from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.configuration.telegram import TelegramSettings
from appointment_bot.core.models import AvailabilityResult
from appointment_bot.reservation_engine.appointments import open_appointment_panel
from appointment_bot.reservation_engine.login import login
from appointment_bot.reservation_engine.monitor import monitor_appointment_availability
from appointment_bot.reservation_engine.ports import ReservationEnginePorts
from appointment_bot.reservation_engine.programs import click_program_action
from appointment_bot.reservation_engine.results import with_client_context
from appointment_bot.reservation_engine.stages import appointment_stage_result, read_process_stages
from appointment_bot.utils.screenshots import save_screenshot

logger = logging.getLogger(__name__)


@dataclass
class SessionFlowResult:
    final_result: AvailabilityResult
    screenshot_path: Path | None
    screenshot_paths: list[Path]


def execute_session_flow(
    page,
    *,
    runtime_settings: RuntimeSettings,
    reservation_settings: ReservationSettings,
    captcha_settings: CaptchaSettings,
    evidence_settings: EvidenceSettings,
    telegram_settings: TelegramSettings,
    run_id: str | None = None,
    order_id: str | None = None,
    client_name: str | None = None,
    cancel_event: threading.Event | None = None,
    on_check: Callable[[AvailabilityResult, int, int | None], None] | None = None,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    on_submission_intent: Callable[[dict | None], None] | None = None,
    on_submission_started: Callable[[dict | None], None] | None = None,
    on_submission_resolved: Callable[[str, str | None, str | None], None] | None = None,
    expected_person_name: str | None = None,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    notify_mode: str = "full",
    ports: ReservationEnginePorts,
) -> SessionFlowResult:
    selected_program_expediente = program_expediente
    selected_program_plate = program_plate

    def remember_selected_program(row: dict[str, object]) -> None:
        nonlocal selected_program_expediente, selected_program_plate
        selected_program_expediente = (
            str(row.get("expediente") or "").strip() or selected_program_expediente
        )
        selected_program_plate = str(row.get("placa") or "").strip() or selected_program_plate

    login(page, reservation_settings=reservation_settings)
    page = click_program_action(
        page,
        on_multiple_programs=lambda details: ports.alerts.notify_programs(
            order_id,
            client_name,
            details,
            runtime_settings=runtime_settings,
            telegram_settings=telegram_settings,
        ),
        on_program_selected=remember_selected_program,
        program_expediente=program_expediente,
        program_plate=program_plate,
    )
    stages = read_process_stages(page)
    stage_result = appointment_stage_result(stages)
    if stage_result is not None:
        stage_result = with_client_context(
            stage_result,
            order_id=order_id,
            client_name=client_name,
            reservation_settings=reservation_settings,
            program_expediente=selected_program_expediente,
            program_plate=selected_program_plate,
        )
        screenshot_path = save_process_stages_snapshot(page, evidence_settings=evidence_settings)
        if notify_mode == "full":
            ports.alerts.notify_result(
                stage_result, screenshot_path, telegram_settings=telegram_settings
            )
        logger.info("Finished appointment check: %s", stage_result.status)
        return SessionFlowResult(stage_result, screenshot_path, [])

    page = open_appointment_panel(page, cancel_event=cancel_event)
    result, screenshot_path, screenshot_paths = monitor_appointment_availability(
        page,
        None,
        cancel_event,
        on_check,
        is_allowed_appointment,
        can_submit,
        can_solve_captcha,
        on_submission_intent,
        on_submission_started,
        on_submission_resolved,
        expected_person_name,
        selected_program_expediente,
        selected_program_plate,
        run_id,
        order_id,
        ports=ports,
        runtime_settings=runtime_settings,
        reservation_settings=reservation_settings,
        captcha_settings=captcha_settings,
        evidence_settings=evidence_settings,
    )
    result = with_client_context(
        result,
        order_id=order_id,
        client_name=client_name,
        reservation_settings=reservation_settings,
        program_expediente=selected_program_expediente,
        program_plate=selected_program_plate,
    )
    if notify_mode == "full":
        ports.alerts.notify_result(
            result,
            screenshot_path,
            screenshot_paths=screenshot_paths,
            telegram_settings=telegram_settings,
        )
    logger.info("Finished appointment check: %s", result.status)
    return SessionFlowResult(result, screenshot_path, screenshot_paths)


def save_process_stages_snapshot(
    page,
    *,
    evidence_settings: EvidenceSettings,
    label: str = "02-detalle-tramite-etapas-reservar-cita",
) -> Path | None:
    return save_screenshot(page, label=label, evidence_settings=evidence_settings)
