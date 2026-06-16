from appointment_bot.config import Settings
from appointment_bot.domain import ResultStatus, RunReport
from appointment_bot.services.database import (
    clear_client_submission_state,
    client_submission_age_seconds,
    get_client,
)

RECONCILABLE_STATUSES = {
    ResultStatus.AVAILABLE,
    ResultStatus.COMPLETED,
    ResultStatus.PARTIAL,
    ResultStatus.UNAVAILABLE,
}


def client_can_submit(client_id: str, settings: Settings) -> bool:
    client = get_client(client_id, settings=settings)
    return client is not None and client.active and not client.done


def reconcile_pending_submission(
    client_id: str,
    report: RunReport,
    settings: Settings,
) -> bool:
    age_seconds = client_submission_age_seconds(client_id, settings=settings)
    if (
        age_seconds is None
        or age_seconds < settings.error_backoff_seconds
        or report.status not in RECONCILABLE_STATUSES
    ):
        return False

    clear_client_submission_state(client_id, settings=settings)
    return True
