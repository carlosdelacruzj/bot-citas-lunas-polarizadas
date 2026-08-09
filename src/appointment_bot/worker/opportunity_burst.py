from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from uuid import uuid4

from appointment_bot.config import Settings
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
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._executor: ThreadPoolExecutor | None = None
        self._candidates: deque[ServiceOrderCandidate] = deque()
        self._futures: dict[Future[BurstExecution], ServiceOrderCandidate] = {}
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

    @property
    def started(self) -> bool:
        with self._lock:
            return self._started

    def maybe_start(self, result: AvailabilityResult) -> bool:
        if not self.settings.opportunity_burst_enabled or not self.settings.auto_reserve:
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
        if self.preferred_order_ids:
            preferred_positions = {
                order_id: index for index, order_id in enumerate(self.preferred_order_ids)
            }
            candidates.sort(
                key=lambda candidate: (
                    candidate.order_id not in preferred_positions,
                    preferred_positions.get(candidate.order_id, len(preferred_positions)),
                )
            )
        candidates = self._distinct_account_candidates(candidates)
        if not candidates:
            return False

        with self._lock:
            if self._started:
                return True
            self._started = True
            self._started_at = time.monotonic()
            self._deadline = self._started_at + self.settings.opportunity_burst_max_seconds
            self._candidates.extend(candidates)
            self._candidate_count = len(candidates)
            self._executor = ThreadPoolExecutor(
                max_workers=self.settings.opportunity_burst_max_sessions,
                thread_name_prefix="opportunity-burst",
            )
            initial_slots = (
                self.settings.opportunity_burst_max_sessions
                - self._active_sessions_locked()
            )
            launched = False
            for _ in range(initial_slots):
                if not self._submit_next_locked():
                    break
                launched = True
            logger.info(
                "Opportunity burst %s started after detector %s with %s candidate(s)",
                self.burst_id,
                self.detector_order.order_id,
                len(candidates),
            )
            return launched

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
            refill, stop_reason = _detector_decision(detector_report)
            if stop_reason is not None:
                self._stop_refills = True
                self._completion_reason = stop_reason
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
        if self._active_sessions_locked() >= self.settings.opportunity_burst_max_sessions:
            return False
        if not self._candidates:
            if self._completion_reason is None:
                self._completion_reason = "candidate_queue_exhausted"
            return False
        if self._executor is None:
            return False

        order = self._candidates.popleft()
        self._scheduled_clients += 1
        future = self._executor.submit(self._run_candidate, order)
        self._futures[future] = order
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

    def _run_candidate(self, order: ServiceOrderCandidate) -> BurstExecution:
        owner_token = f"{self.burst_id}-{uuid4().hex}"
        try:
            claimed = claim_service_order(
                order.order_id,
                owner_token=owner_token,
                lease_seconds=SERVICE_ORDER_LEASE_SECONDS,
                settings=self.settings,
            )
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
            )

        try:
            report = run_service_order(
                self.settings,
                order,
                lease_owner=owner_token,
                burst_mode=True,
                cancel_event=self.cancel_event,
            )
            return BurstExecution(order=order, report=report, claim_acquired=True)
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
        order = self._futures.get(future)
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

        with self._condition:
            self._futures.pop(future, None)
            self._executions.append(execution)
            if refill:
                self._confirmed_order_ids.append(execution.order.order_id)
            if stop_reason is not None:
                self._stop_refills = True
                self._completion_reason = stop_reason
            elif refill:
                self._submit_next_locked()
            elif not execution.claim_acquired:
                self._scheduled_clients -= 1
                self._submit_next_locked()
            self._condition.notify_all()


def _detector_decision(report: RunReport) -> tuple[bool, str | None]:
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
