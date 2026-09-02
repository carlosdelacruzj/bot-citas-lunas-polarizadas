from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from appointment_bot.config import Settings
from appointment_bot.core.models import AvailabilityResult, RunReport
from appointment_bot.db.captcha_authority import resolve_captcha_authority_decision
from appointment_bot.db.captcha_sampling_control import get_captcha_sampling_control
from appointment_bot.db.opportunity_bursts import record_burst_event
from appointment_bot.db.opportunity_controls import (
    is_opportunity_admission_allowed,
    trip_opportunity_circuit_breaker,
)
from appointment_bot.db.orders import record_order_program_listing
from appointment_bot.reports.run_reporting import finalize_report, report_from_result
from appointment_bot.reservation_engine.ports import (
    CaptchaSolveResult,
    ReservationEnginePorts,
    SessionVideo,
)
from appointment_bot.services.captcha import solve_normal_captcha
from appointment_bot.services.captcha_authority import solve_reservation_captcha
from appointment_bot.services.captcha_shadow import (
    enqueue_shadow_external_result,
    enqueue_shadow_prediction,
)
from appointment_bot.services.client_video import ClientSessionVideoRecorder
from appointment_bot.services.notifier import notify_error, notify_result, send_telegram_message
from appointment_bot.services.telegram_alerts import enqueue_generic_telegram_alert

logger = logging.getLogger(__name__)


class WorkerRunSink:
    def report_from_result(self, result: AvailabilityResult, **kwargs: Any) -> RunReport:
        return report_from_result(result, **kwargs)

    def finalize_report(
        self,
        report: RunReport,
        settings: Settings,
        *,
        started_at_dt: datetime,
    ) -> RunReport:
        return finalize_report(report, settings, started_at_dt=started_at_dt)

    def create_video(
        self,
        settings: Settings,
        *,
        order_id: str | None,
        client_name: str | None,
        started_at: datetime,
    ) -> SessionVideo | None:
        return ClientSessionVideoRecorder.create(
            settings,
            order_id=order_id,
            client_name=client_name,
            started_at=started_at,
        )


class WorkerAlertSink:
    def notify_result(
        self,
        result: AvailabilityResult,
        settings: Settings,
        screenshot_path: Path | None,
        *,
        screenshot_paths: list[Path] | None = None,
    ) -> None:
        notify_result(
            result,
            settings,
            screenshot_path,
            screenshot_paths=screenshot_paths,
        )

    def notify_error(
        self,
        error: Exception,
        settings: Settings,
        screenshot_path: Path | None,
    ) -> None:
        notify_error(error, settings, screenshot_path)

    def notify_programs(
        self,
        settings: Settings,
        order_id: str | None,
        client_name: str | None,
        details: dict[str, Any],
    ) -> None:
        should_notify = True
        if order_id is not None:
            try:
                should_notify = record_order_program_listing(
                    order_id,
                    details,
                    settings=settings,
                )
            except Exception:
                logger.exception("Could not persist program listing for %s", order_id)
        if not should_notify:
            logger.info("Program listing unchanged for %s; skipping alert", order_id)
            return
        try:
            send_telegram_message(
                settings,
                _program_notification_text(order_id, client_name, details),
            )
        except Exception:
            logger.exception("Could not notify program listing")

    def graphic_captcha_returned(self) -> None:
        enqueue_generic_telegram_alert(
            "⚠️ El portal volvió a mostrar un CAPTCHA gráfico. La reserva seguirá "
            "usando 2Captcha; V3/V6 permanecen en reserva fría hasta una "
            "reactivación explícita.",
            dedupe_key=(
                f"captcha-graphic-returned:{datetime.now(UTC).strftime('%Y-%m')}"
            ),
        )


class WorkerCaptchaAuthority:
    def solve(
        self,
        image_path: Path,
        settings: Settings,
        **kwargs: Any,
    ) -> CaptchaSolveResult:
        result = solve_reservation_captcha(
            image_path,
            settings,
            fallback_solver=solve_normal_captcha,
            **kwargs,
        )
        return CaptchaSolveResult(**vars(result))

    def enqueue_prediction(self, **kwargs: Any) -> bool:
        return enqueue_shadow_prediction(**kwargs)

    def enqueue_external_result(self, **kwargs: Any) -> bool:
        return enqueue_shadow_external_result(**kwargs)

    def resolve_portal_outcome(self, event_id: str, *, portal_outcome: str) -> None:
        resolve_captcha_authority_decision(event_id, portal_outcome=portal_outcome)

    def sample_limit(self, settings: Settings) -> int:
        return get_captcha_sampling_control(settings).effective_sample_limit


class WorkerOpportunityControl:
    def admission_allowed(self, feature: str, settings: Settings) -> bool:
        return bool(is_opportunity_admission_allowed(feature, settings=settings))

    def record_event(self, **kwargs: Any) -> None:
        record_burst_event(**kwargs)

    def trip_breaker(
        self,
        reason: str,
        burst_id: str | None,
        settings: Settings,
    ) -> None:
        trip_opportunity_circuit_breaker(
            reason=reason,
            burst_id=burst_id,
            settings=settings,
        )


def build_reservation_engine_ports() -> ReservationEnginePorts:
    return ReservationEnginePorts(
        runs=WorkerRunSink(),
        alerts=WorkerAlertSink(),
        captcha=WorkerCaptchaAuthority(),
        opportunities=WorkerOpportunityControl(),
    )


def _program_notification_text(
    order_id: str | None,
    client_name: str | None,
    details: dict[str, Any],
) -> str:
    rows = details.get("rows") if isinstance(details.get("rows"), list) else []
    pending_count = int(details.get("pending_count") or 0)
    title = (
        "UN SOLO TRAMITE PENDIENTE"
        if pending_count == 1
        else "MULTIPLES TRAMITES PENDIENTES DETECTADOS"
        if pending_count > 1
        else "LISTADO SIN TRAMITES PENDIENTES"
    )
    lines = [title, f"Orden: {order_id or 'observer'}"]
    if client_name:
        lines.append(f"Cliente: {client_name}")
    lines.extend(
        [
            f"Tramites: {details.get('program_count')}",
            f"Pendientes: {details.get('pending_count')}",
        ]
    )
    decision_messages = {
        "single_pending_selected": "Accion: se eligio el unico PENDIENTE",
        "multiple_pending_blocked": (
            "Accion: detenido; elegir uno o todos desde Dashboard o Telegram"
        ),
        "target_selected": "Accion: se eligio el tramite objetivo",
        "target_not_found": "Accion: detenido; no se encontro el tramite objetivo",
        "target_not_pending": "Accion: detenido; el tramite objetivo no esta PENDIENTE",
        "target_ambiguous": "Accion: detenido; el objetivo coincide con varios PENDIENTE",
        "program_rows_unavailable": (
            "Accion: detenido; no se pudo leer el listado completo de tramites"
        ),
        "no_pending_blocked": "Accion: detenido sin PENDIENTE",
    }
    decision_message = decision_messages.get(str(details.get("decision") or "").strip())
    if decision_message:
        lines.append(decision_message)
    for index, row in enumerate(rows[:5], start=1):
        if not isinstance(row, dict):
            continue
        vehicle = " ".join(
            str(row.get(key) or "").strip()
            for key in ("placa", "marca", "modelo", "color")
            if str(row.get(key) or "").strip()
        )
        status = str(row.get("status") or "sin estado").strip()
        expediente = str(row.get("expediente") or "").strip()
        lines.append(
            f"{index}. {status}"
            + (f" exp {expediente}" if expediente else "")
            + (f" - {vehicle}" if vehicle else "")
        )
    return "\n".join(lines)
