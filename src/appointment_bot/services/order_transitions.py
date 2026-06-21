from appointment_bot.config import Settings
from appointment_bot.domain import ResultStatus, RunReport
from appointment_bot.services.postgres_database import (
    clear_order_submission_state,
    get_service_order_runtime,
    order_submission_age_seconds,
    service_order_claim_owned,
)

RECONCILABLE_STATUSES = {
    ResultStatus.AVAILABLE,
    ResultStatus.COMPLETED,
    ResultStatus.PARTIAL,
    ResultStatus.UNAVAILABLE,
}


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
    age_seconds = order_submission_age_seconds(order_id, settings=settings)
    if (
        age_seconds is None
        or age_seconds < settings.error_backoff_seconds
        or report.status not in RECONCILABLE_STATUSES
    ):
        return False

    clear_order_submission_state(order_id, settings=settings)
    return True
