from appointment_bot.config import Settings
from appointment_bot.db.orders import (
    clear_order_submission_state,
    get_service_order_runtime,
    service_order_claim_owned,
)
from appointment_bot.db.reservations import (
    get_active_reservation_attempt,
    resolve_reservation_attempt,
)
from appointment_bot.domain import ResultStatus, RunReport
from appointment_bot.utils.sanitization import normalize_option


def order_can_submit(order_id: str, owner_token: str, settings: Settings) -> bool:
    order = get_service_order_runtime(order_id, settings=settings)
    return (
        order is not None
        and order.status == "ready"
        and service_order_claim_owned(
            order_id,
            owner_token=owner_token,
            settings=settings,
        )
    )


def reconcile_pending_submission(
    order_id: str,
    report: RunReport,
    settings: Settings,
) -> bool:
    attempt = get_active_reservation_attempt(order_id, settings=settings)
    if attempt is None:
        return False
    details = report.details or {}
    portal_text = normalize_option(
        " ".join(
            str(details.get(key) or "") for key in ("fecha", "hora", "mensaje", "estado")
        )
    )
    expected_date = normalize_option(str(attempt.get("appointment_date") or ""))
    expected_hour = normalize_option(str(attempt.get("appointment_hour") or ""))
    terminal_status = normalize_option(str(details.get("estado") or ""))
    exact_programmed = (
        report.status == ResultStatus.REGISTERED
        or (
            report.status == ResultStatus.COMPLETED
            and terminal_status in {"programado", "atendido"}
            and bool(expected_date)
            and bool(expected_hour)
            and expected_date in portal_text
            and expected_hour in portal_text
        )
    )
    if not exact_programmed:
        if report.status in {
            ResultStatus.AVAILABLE,
            ResultStatus.PARTIAL,
            ResultStatus.UNAVAILABLE,
        }:
            resolve_reservation_attempt(
                str(attempt["attempt_id"]),
                "rejected",
                run_id=report.run_id,
                evidence_path=report.screenshot_path,
                settings=settings,
            )
            clear_order_submission_state(order_id, settings=settings)
            return True
        resolve_reservation_attempt(
            str(attempt["attempt_id"]),
            "unknown",
            run_id=report.run_id,
            evidence_path=report.screenshot_path,
            settings=settings,
        )
        return False
    resolve_reservation_attempt(
        str(attempt["attempt_id"]),
        "confirmed",
        run_id=report.run_id,
        evidence_path=report.screenshot_path,
        settings=settings,
    )
    clear_order_submission_state(order_id, settings=settings)
    return True
