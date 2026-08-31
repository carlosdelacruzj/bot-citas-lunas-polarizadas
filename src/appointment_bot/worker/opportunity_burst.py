from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from appointment_bot.config import OPPORTUNITY_BURST_SESSION_LIMIT, Settings
from appointment_bot.core.models import (
    AvailabilityResult,
    RunReport,
    ServiceOrderCandidate,
    ServiceOrderRuntime,
)
from appointment_bot.db.orders import (
    claim_service_order,
    list_compatible_orders_for_opportunities,
    mark_order_done,
    release_service_order_claim,
    update_order_state,
)
from appointment_bot.services.order_runtime import (
    OrderReportOutcome,
    classify_order_report,
    order_done_status_from_report,
)
from appointment_bot.worker.order_execution import (
    SERVICE_ORDER_LEASE_SECONDS,
    run_service_order,
)
from appointment_bot.worker.order_results import observed_opportunities
from appointment_bot.worker.queue_policy import update_state_from_report
from appointment_bot.worker.recovery import portal_defense_signal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BurstExecution:
    order: ServiceOrderCandidate
    report: RunReport
    claim_acquired: bool
    execution_id: str | None = None


@dataclass(frozen=True)
class OpportunityBurstResult:
    started: bool
    burst_id: str | None = None
    executions: tuple[BurstExecution, ...] = ()
    confirmed_order_ids: tuple[str, ...] = ()
    max_active_sessions: int = 0
    candidate_count: int = 0
    scheduled_clients: int = 0
    duration_seconds: float = 0.0
    completion_reason: str = "not_started"

    def summary_report(self) -> RunReport:
        failed = sum(
            execution.report.status in {"error", "unknown", "reservation_unconfirmed"}
            or execution.report.exit_code != 0
            for execution in self.executions
        )
        return RunReport(
            status="error" if failed else "completed",
            message=(
                "Rafaga de oportunidades finalizada. "
                f"Auxiliares ejecutados: {len(self.executions)}. "
                f"Reservas auxiliares confirmadas: {len(self.confirmed_order_ids)}. "
                f"Cierre: {self.completion_reason}."
            ),
            exit_code=1 if failed else 0,
            details={
                "opportunity_burst": True,
                "burst_id": self.burst_id,
                "completion_reason": self.completion_reason,
                "auxiliary_executions": len(self.executions),
                "confirmed_reservations": len(self.confirmed_order_ids),
                "confirmed_order_ids": list(self.confirmed_order_ids),
                "max_active_sessions": self.max_active_sessions,
                "compatible_candidates": self.candidate_count,
                "scheduled_clients": self.scheduled_clients,
                "duration_seconds": self.duration_seconds,
                "results": [
                    {
                        "order_id": execution.order.order_id,
                        "status": execution.report.status,
                        "claim_acquired": execution.claim_acquired,
                    }
                    for execution in self.executions
                ],
            },
        )


class OpportunityBurstCoordinator:
    def __init__(
        self,
        settings: Settings,
        detector_order: ServiceOrderCandidate | ServiceOrderRuntime,
        *,
        cancel_event: threading.Event | None = None,
        preferred_order_ids: tuple[str, ...] = (),
    ) -> None:
        self.settings = settings
        self.detector_order = detector_order
        self.cancel_event = cancel_event
        self.preferred_order_ids = preferred_order_ids
        self.burst_id = f"burst-{uuid4().hex}"
        self.detector_execution_id = f"burst-execution-{uuid4().hex}"
        self.detector_context: dict[str, str] = {}
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._executor: ThreadPoolExecutor | None = None
        self._candidates: deque[ServiceOrderCandidate] = deque()
        self._futures: dict[Future[BurstExecution], tuple[ServiceOrderCandidate, str]] = {}
        self._executions: list[BurstExecution] = []
        self._confirmed_order_ids: list[str] = []
        self._started_at: float | None = None
        self._deadline: float | None = None
        self._detector_active = True
        self._started = False
        self._stop_refills = False
        self._completion_reason: str | None = None
        self._scheduled_clients = 1
        self._max_active_sessions = 1
        self._candidate_count = 0
        self._candidate_ids: dict[str, str] = {}
        self._last_admitted_candidate_id: str | None = None
        self._last_admitted_execution_id: str | None = None

    @property
    def started(self) -> bool:
        with self._lock:
            return self._started

    def maybe_start(self, result: AvailabilityResult) -> bool:
        if not self.settings.auto_reserve:
            return False
        if self.cancel_event is not None and self.cancel_event.is_set():
            return False
        if result.status != "available":
            return False
        details = dict(result.details or {})
        if details.get("fetch_probe") or details.get("blocked_by_order_rule"):
            return False
        opportunities = observed_opportunities(details)
        if not opportunities:
            return False
        if not _admission_allowed("obs006", self.settings):
            return False

        with self._lock:
            if self._started:
                return True

        candidate_limit = (
            None
            if self.settings.opportunity_burst_max_clients == 0
            else max(self.settings.opportunity_burst_max_clients - 1, 0)
        )
        candidates = list_compatible_orders_for_opportunities(
            opportunities,
            exclude_order_ids={self.detector_order.order_id},
            limit=candidate_limit,
            settings=self.settings,
        )
        candidates = self._distinct_account_candidates(candidates)
        if not candidates:
            return False

        candidate_snapshot = [
            {
                "queue_position": position,
                "order_id": candidate.order_id,
                "priority_snapshot": candidate.priority,
                "selection_source": (
                    "preferred"
                    if candidate.order_id in self.preferred_order_ids
                    else "ranked"
                ),
            }
            for position, candidate in enumerate(candidates, start=1)
        ]
        try:
            self.detector_execution_id, self._candidate_ids = _create_burst(
                burst_id=self.burst_id,
                detector_order_id=self.detector_order.order_id,
                candidates=candidate_snapshot,
                opportunities=[
                    {"date": date_text, "hour": hour_text}
                    for date_text, hour_text in opportunities
                ],
                settings=self.settings,
            )
        except Exception:
            logger.exception("Could not persist opportunity burst %s", self.burst_id)
            _trip_breaker("persistence_failed", self.burst_id, self.settings)
            return False

        with self._lock:
            if self._started:
                return True
            self._started = True
            self._started_at = time.monotonic()
            self._deadline = self._started_at + self.settings.opportunity_burst_max_seconds
            self._candidates.extend(candidates)
            self._candidate_count = len(candidates)
            self.detector_context.update(
                {
                    "burst_id": self.burst_id,
                    "execution_id": self.detector_execution_id,
                    "burst_role": "detector",
                }
            )
            self._last_admitted_execution_id = self.detector_execution_id
            self._executor = ThreadPoolExecutor(
                max_workers=min(
                    self.settings.opportunity_burst_max_sessions,
                    OPPORTUNITY_BURST_SESSION_LIMIT,
                ),
                thread_name_prefix="opportunity-burst",
            )
            initial_slots = (
                min(
                    self.settings.opportunity_burst_max_sessions,
                    OPPORTUNITY_BURST_SESSION_LIMIT,
                )
                - self._active_sessions_locked()
            )
            for _ in range(initial_slots):
                if not self._submit_next_locked():
                    break
            logger.info(
                "Opportunity burst %s started after detector %s with %s candidate(s)",
                self.burst_id,
                self.detector_order.order_id,
                len(candidates),
            )
            return True

    def finish_detector(
        self,
        detector_report: RunReport,
        *,
        on_wait: Callable[[], None] | None = None,
    ) -> OpportunityBurstResult:
        with self._lock:
            if not self._started:
                return OpportunityBurstResult(started=False)
            self._detector_active = False
            try:
                _finish_execution(
                    execution_id=self.detector_execution_id,
                    run_id=detector_report.run_id,
                    status=detector_report.status,
                    result_details=dict(detector_report.details or {}),
                    exit_code=detector_report.exit_code,
                    exit_reason=_report_exit_reason(detector_report),
                    settings=self.settings,
                )
            except Exception:
                logger.exception("Could not persist detector burst execution")
                self._stop_refills = True
                self._completion_reason = "persistence_failed"
                _trip_breaker("persistence_failed", self.burst_id, self.settings)
            refill, stop_reason = _detector_decision(detector_report)
            if stop_reason is not None:
                self._stop_refills = True
                self._completion_reason = stop_reason
                if _is_breaker_reason(stop_reason):
                    _trip_breaker(stop_reason, self.burst_id, self.settings)
            elif refill:
                self._submit_next_locked()
            self._condition.notify_all()

        while True:
            with self._condition:
                if not self._futures:
                    break
                self._condition.wait(timeout=1)
            if on_wait is not None:
                on_wait()

        executor = self._executor
        if executor is not None:
            executor.shutdown(wait=True)
        duration = (
            round(time.monotonic() - self._started_at, 3)
            if self._started_at is not None
            else 0.0
        )
        completion_reason = self._completion_reason
        if completion_reason is None:
            completion_reason = (
                "client_limit"
                if self._client_limit_reached_locked()
                else "sessions_finished"
            )
        try:
            _finish_burst(
                burst_id=self.burst_id,
                completion_reason=completion_reason,
                max_active_sessions=self._max_active_sessions,
                settings=self.settings,
            )
        except Exception:
            logger.exception("Could not finalize opportunity burst %s", self.burst_id)
            _trip_breaker("persistence_failed", self.burst_id, self.settings)
        return OpportunityBurstResult(
            started=True,
            burst_id=self.burst_id,
            executions=tuple(self._executions),
            confirmed_order_ids=tuple(self._confirmed_order_ids),
            max_active_sessions=self._max_active_sessions,
            candidate_count=self._candidate_count,
            scheduled_clients=self._scheduled_clients,
            duration_seconds=duration,
            completion_reason=completion_reason,
        )

    def _distinct_account_candidates(
        self,
        candidates: list[ServiceOrderCandidate],
    ) -> list[ServiceOrderCandidate]:
        usernames = {self.detector_order.username.strip().casefold()}
        distinct: list[ServiceOrderCandidate] = []
        for candidate in candidates:
            username = candidate.username.strip().casefold()
            if not username or username in usernames:
                continue
            usernames.add(username)
            distinct.append(candidate)
        return distinct

    def _active_sessions_locked(self) -> int:
        return len(self._futures) + int(self._detector_active)

    def _client_limit_reached_locked(self) -> bool:
        max_clients = self.settings.opportunity_burst_max_clients
        return max_clients > 0 and self._scheduled_clients >= max_clients

    def _submit_next_locked(self) -> bool:
        if self._stop_refills or (
            self.cancel_event is not None and self.cancel_event.is_set()
        ):
            return False
        if self._deadline is not None and time.monotonic() >= self._deadline:
            self._completion_reason = "burst_window_expired"
            return False
        if self._client_limit_reached_locked():
            return False
        if self._active_sessions_locked() >= min(
            self.settings.opportunity_burst_max_sessions,
            OPPORTUNITY_BURST_SESSION_LIMIT,
        ):
            return False
        if not self._candidates:
            if self._completion_reason is None:
                self._completion_reason = "candidate_queue_exhausted"
            return False
        if self._executor is None:
            return False
        if not _admission_allowed("obs006", self.settings):
            self._stop_refills = True
            self._completion_reason = "admission_closed"
            return False

        order = self._candidates.popleft()
        position = self._scheduled_clients + 1
        try:
            execution_id = _create_execution(
                burst_id=self.burst_id,
                position=position,
                role="auxiliary",
                order_id=order.order_id,
                candidate_id=self._candidate_ids[order.order_id],
                previous_candidate_id=self._last_admitted_candidate_id,
                previous_execution_id=self._last_admitted_execution_id,
                settings=self.settings,
            )
        except Exception:
            logger.exception("Could not persist auxiliary burst admission")
            self._stop_refills = True
            self._completion_reason = "persistence_failed"
            _trip_breaker("persistence_failed", self.burst_id, self.settings)
            return False
        self._last_admitted_candidate_id = self._candidate_ids[order.order_id]
        self._last_admitted_execution_id = execution_id
        self._scheduled_clients += 1
        future = self._executor.submit(self._run_candidate, order, execution_id)
        self._futures[future] = (order, execution_id)
        self._max_active_sessions = max(
            self._max_active_sessions,
            self._active_sessions_locked(),
        )
        future.add_done_callback(self._future_done)
        logger.info(
            "Opportunity burst %s launched auxiliary order %s "
            "(%s clients scheduled, %s candidate(s) remaining)",
            self.burst_id,
            order.order_id,
            self._scheduled_clients,
            len(self._candidates),
        )
        return True

    def _run_candidate(
        self,
        order: ServiceOrderCandidate,
        execution_id: str,
    ) -> BurstExecution:
        owner_token = f"{self.burst_id}-{uuid4().hex}"
        try:
            _start_execution(execution_id, self.settings)
        except Exception:
            logger.exception("Could not mark burst execution as started")
            _trip_breaker("persistence_failed", self.burst_id, self.settings)
            return BurstExecution(
                order=order,
                report=RunReport(
                    status="error",
                    message="No se pudo registrar el inicio durable de la rafaga.",
                    exit_code=1,
                    order_id=order.order_id,
                ),
                claim_acquired=False,
                execution_id=execution_id,
            )
        try:
            claimed = claim_service_order(
                order.order_id,
                owner_token=owner_token,
                lease_seconds=SERVICE_ORDER_LEASE_SECONDS,
                settings=self.settings,
            )
            _start_execution(execution_id, self.settings, claim_acquired=claimed)
        except Exception as exc:
            logger.exception("Opportunity burst could not claim order %s", order.order_id)
            return BurstExecution(
                order=order,
                report=RunReport(
                    status="error",
                    message=f"No se pudo reclamar la orden para la rafaga: {exc}",
                    exit_code=1,
                    order_id=order.order_id,
                ),
                claim_acquired=False,
                execution_id=execution_id,
            )
        if not claimed:
            return BurstExecution(
                order=order,
                report=RunReport(
                    status="skipped",
                    message="Otra ejecucion reclamo la orden antes de iniciar la rafaga.",
                    exit_code=0,
                    order_id=order.order_id,
                ),
                claim_acquired=False,
                execution_id=execution_id,
            )

        try:
            first_check_recorded = False

            def on_auxiliary_check(_result, *_args) -> None:
                nonlocal first_check_recorded
                if first_check_recorded:
                    return
                first_check_recorded = True
                _mark_first_check(execution_id, self.settings)

            report = run_service_order(
                self.settings,
                order,
                lease_owner=owner_token,
                burst_mode=True,
                cancel_event=self.cancel_event,
                on_check=on_auxiliary_check,
                opportunity_context={
                    "burst_id": self.burst_id,
                    "execution_id": execution_id,
                    "burst_role": "auxiliary",
                },
            )
            return BurstExecution(
                order=order,
                report=report,
                claim_acquired=True,
                execution_id=execution_id,
            )
        finally:
            try:
                released = release_service_order_claim(
                    order.order_id,
                    owner_token=owner_token,
                    settings=self.settings,
                )
            except Exception:
                logger.exception(
                    "Opportunity burst could not release claim for %s",
                    order.order_id,
                )
            else:
                if not released:
                    logger.warning(
                        "Opportunity burst claim was no longer owned during release: %s",
                        order.order_id,
                    )

    def _future_done(self, future: Future[BurstExecution]) -> None:
        future_context = self._futures.get(future)
        order = future_context[0] if future_context is not None else None
        execution_id = future_context[1] if future_context is not None else None
        try:
            execution = future.result()
        except Exception as exc:
            logger.exception("Unexpected opportunity burst execution failure")
            if order is None:
                return
            execution = BurstExecution(
                order=order,
                report=RunReport(
                    status="error",
                    message=f"Fallo inesperado de la rafaga: {exc}",
                    exit_code=1,
                    order_id=order.order_id,
                ),
                claim_acquired=False,
                execution_id=execution_id,
            )

        refill = False
        stop_reason = None
        try:
            refill, stop_reason = _apply_auxiliary_result(self.settings, execution)
        except Exception:
            logger.exception(
                "Could not apply opportunity burst result for %s",
                execution.order.order_id,
            )
            stop_reason = "result_transition_failed"

        try:
            if execution.execution_id is not None:
                _finish_execution(
                    execution_id=execution.execution_id,
                    run_id=execution.report.run_id,
                    status=execution.report.status,
                    result_details=dict(execution.report.details or {}),
                    exit_code=execution.report.exit_code,
                    exit_reason=stop_reason or _report_exit_reason(execution.report),
                    settings=self.settings,
                )
        except Exception:
            logger.exception("Could not persist completed burst execution")
            stop_reason = "persistence_failed"

        with self._condition:
            self._futures.pop(future, None)
            self._executions.append(execution)
            if refill:
                self._confirmed_order_ids.append(execution.order.order_id)
            if stop_reason is not None:
                self._stop_refills = True
                self._completion_reason = stop_reason
                if _is_breaker_reason(stop_reason):
                    _trip_breaker(stop_reason, self.burst_id, self.settings)
            elif refill:
                self._submit_next_locked()
            elif not execution.claim_acquired:
                self._scheduled_clients -= 1
                self._submit_next_locked()
            self._condition.notify_all()


def _admission_allowed(control_name: str, settings: Settings) -> bool:
    try:
        from appointment_bot.db.opportunity_controls import (
            is_opportunity_admission_allowed,
        )

        return bool(is_opportunity_admission_allowed(control_name, settings=settings))
    except Exception:
        logger.exception("Could not read %s opportunity admission control", control_name)
        return False


def _trip_breaker(reason: str, burst_id: str | None, settings: Settings) -> None:
    try:
        from appointment_bot.db.opportunity_controls import (
            trip_opportunity_circuit_breaker,
        )

        trip_opportunity_circuit_breaker(
            reason=reason,
            burst_id=burst_id,
            settings=settings,
        )
    except Exception:
        logger.exception("Could not trip opportunity circuit breaker: %s", reason)


def _create_burst(
    *,
    burst_id: str,
    detector_order_id: str,
    candidates: list[dict],
    opportunities: list[dict],
    settings: Settings,
) -> tuple[str, dict[str, str]]:
    from appointment_bot.db.opportunity_bursts import (
        create_burst_execution,
        create_opportunity_burst,
        record_burst_candidates,
    )

    started_at = datetime.now(UTC)
    persisted_id = create_opportunity_burst(
        detector_order_id=detector_order_id,
        started_at=started_at,
        admission_deadline_at=(
            started_at + timedelta(seconds=settings.opportunity_burst_max_seconds)
        ),
        opportunities=opportunities,
        configured_max_sessions=min(
            settings.opportunity_burst_max_sessions,
            OPPORTUNITY_BURST_SESSION_LIMIT,
        ),
        configured_max_clients=settings.opportunity_burst_max_clients,
        config={
            "max_sessions": min(
                settings.opportunity_burst_max_sessions,
                OPPORTUNITY_BURST_SESSION_LIMIT,
            ),
            "max_clients": settings.opportunity_burst_max_clients,
            "max_seconds": settings.opportunity_burst_max_seconds,
            "session_seconds": settings.opportunity_burst_session_seconds,
            "attempts": settings.opportunity_burst_attempts,
        },
        burst_id=burst_id,
        settings=settings,
    )
    prepared_candidates = [
        {
            **candidate,
            "candidate_id": f"{persisted_id}:candidate:{index}",
            "compatible_opportunities": opportunities,
        }
        for index, candidate in enumerate(candidates, start=1)
    ]
    record_burst_candidates(persisted_id, prepared_candidates, settings=settings)
    execution_id = create_burst_execution(
        burst_id=persisted_id,
        role="detector",
        execution_position=0,
        order_id=detector_order_id,
        settings=settings,
    )
    _start_execution(execution_id, settings, claim_acquired=True)
    _mark_first_check(execution_id, settings)
    return execution_id, {
        str(candidate["order_id"]): str(candidate["candidate_id"])
        for candidate in prepared_candidates
    }


def _create_execution(
    *,
    burst_id: str,
    position: int,
    role: str,
    order_id: str,
    candidate_id: str,
    previous_candidate_id: str | None,
    previous_execution_id: str | None,
    settings: Settings,
) -> str:
    from appointment_bot.db.opportunity_bursts import create_burst_execution

    return create_burst_execution(
        burst_id=burst_id,
        role=role,
        execution_position=position - 1,
        order_id=order_id,
        candidate_id=candidate_id,
        previous_candidate_id=previous_candidate_id,
        previous_execution_id=previous_execution_id,
        settings=settings,
    )


def _start_execution(
    execution_id: str,
    settings: Settings,
    *,
    claim_acquired: bool | None = None,
) -> None:
    from appointment_bot.db.opportunity_bursts import mark_burst_execution_started

    mark_burst_execution_started(
        execution_id,
        claim_acquired=claim_acquired,
        started_at=datetime.now(UTC),
        settings=settings,
    )


def _mark_first_check(execution_id: str, settings: Settings) -> None:
    try:
        from appointment_bot.db.opportunity_bursts import update_burst_execution

        update_burst_execution(
            execution_id,
            first_read_at=datetime.now(UTC),
            settings=settings,
        )
    except Exception:
        logger.exception("Could not persist first check for burst execution %s", execution_id)


def _finish_execution(
    *,
    execution_id: str,
    run_id: str | None,
    status: str,
    result_details: dict,
    exit_code: int,
    exit_reason: str | None,
    settings: Settings,
) -> None:
    from appointment_bot.db.opportunity_bursts import mark_burst_execution_finished

    mark_burst_execution_finished(
        execution_id,
        result_status=status,
        exit_code=exit_code,
        exit_cause=exit_reason,
        run_id=run_id,
        lease_lost=bool(result_details.get("lease_lost")),
        reservation_timing=result_details.get("reservation_timing"),
        finished_at=datetime.now(UTC),
        settings=settings,
    )


def _finish_burst(
    *,
    burst_id: str,
    completion_reason: str,
    max_active_sessions: int,
    settings: Settings,
) -> None:
    from appointment_bot.db.opportunity_bursts import finish_opportunity_burst

    finish_opportunity_burst(
        burst_id,
        completion_reason=completion_reason,
        max_active_sessions=max_active_sessions,
        status="closed",
        circuit_reason=completion_reason if _is_breaker_reason(completion_reason) else None,
        finished_at=datetime.now(UTC),
        settings=settings,
    )


def _report_exit_reason(report: RunReport) -> str | None:
    defense = portal_defense_signal(report.message)
    if defense is not None:
        return f"portal_defense:{defense}"
    if report.status in {"error", "unknown", "reservation_unconfirmed"}:
        return report.status
    return None


def _is_breaker_reason(reason: str) -> bool:
    return reason.startswith("portal_defense:") or reason in {
        "claim_failed",
        "coordinator_failed",
        "auxiliary_reservation_unconfirmed",
        "detector_reservation_unconfirmed",
        "lease_lost",
        "persistence_failed",
        "result_transition_failed",
        "reservation_unconfirmed",
    }


def _detector_decision(report: RunReport) -> tuple[bool, str | None]:
    if bool((report.details or {}).get("lease_lost")):
        return False, "lease_lost"
    defense = portal_defense_signal(report.message)
    if defense is not None:
        return False, f"portal_defense:{defense}"
    outcome = classify_order_report(report)
    if outcome is OrderReportOutcome.REGISTERED:
        return True, None
    if outcome is OrderReportOutcome.RESERVATION_UNCONFIRMED:
        return False, "detector_reservation_unconfirmed"
    if outcome is OrderReportOutcome.FAILURE:
        return False, "detector_technical_error"
    return False, None


def _apply_auxiliary_result(
    settings: Settings,
    execution: BurstExecution,
) -> tuple[bool, str | None]:
    order = execution.order
    report = execution.report
    if bool((report.details or {}).get("lease_lost")):
        return False, "lease_lost"
    if not execution.claim_acquired:
        if report.status == "error":
            return False, "claim_failed"
        return False, None

    defense = portal_defense_signal(report.message)
    if defense is not None:
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            backoff_seconds=None,
            settings=settings,
        )
        return False, f"portal_defense:{defense}"

    update_state_from_report(settings, order, report)
    outcome = classify_order_report(report)
    if outcome is OrderReportOutcome.REGISTERED:
        mark_order_done(order.order_id, settings=settings)
        return True, None
    if outcome is OrderReportOutcome.TERMINAL_STAGE:
        mark_order_done(
            order.order_id,
            status=order_done_status_from_report(report),
            settings=settings,
        )
        return False, None
    if outcome is OrderReportOutcome.CAPTCHA_REJECTED:
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            backoff_seconds=settings.captcha_rejection_cooldown_seconds,
            settings=settings,
        )
        return False, None
    if outcome is OrderReportOutcome.RESERVATION_UNCONFIRMED:
        update_order_state(
            order.order_id,
            status=report.status,
            message=report.message,
            exit_code=report.exit_code,
            backoff_seconds=settings.error_backoff_seconds,
            settings=settings,
        )
        return False, "auxiliary_reservation_unconfirmed"
    if outcome is OrderReportOutcome.FAILURE:
        return False, "auxiliary_technical_error"
    return False, None
