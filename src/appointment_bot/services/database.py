from __future__ import annotations

from collections.abc import Iterable

from appointment_bot.config import Settings, load_settings
from appointment_bot.services import postgres_database
from appointment_bot.services.database_models import (
    Client,
    ClientSummary,
    RunDetail,
    RunRecord,
    RunSummary,
    WorkerState,
)

SCHEMA_VERSION = postgres_database.SCHEMA_VERSION


def init_database(settings: Settings | None = None) -> None:
    postgres_database.init_database(settings)


def add_client(
    client_id: str,
    name: str,
    username: str,
    password: str,
    priority: int,
    *,
    settings: Settings | None = None,
) -> None:
    postgres_database.add_client(
        client_id,
        name,
        username,
        password,
        priority,
        settings=settings,
    )


def list_clients(settings: Settings | None = None) -> list[Client]:
    return postgres_database.list_clients(settings)


def list_client_summaries(settings: Settings | None = None) -> list[ClientSummary]:
    return postgres_database.list_client_summaries(settings)


def get_client(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> Client | None:
    return postgres_database.get_client(client_id, settings=settings)


def update_client(
    client_id: str,
    *,
    name: str | None = None,
    username: str | None = None,
    password: str | None = None,
    priority: int | None = None,
    settings: Settings | None = None,
) -> None:
    postgres_database.update_client(
        client_id,
        name=name,
        username=username,
        password=password,
        priority=priority,
        settings=settings,
    )


def list_active_clients(settings: Settings | None = None) -> list[Client]:
    return postgres_database.list_active_clients(settings)


def client_backoff_seconds(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> int:
    return postgres_database.client_backoff_seconds(client_id, settings=settings)


def client_reservation_pending(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> bool:
    return postgres_database.client_reservation_pending(client_id, settings=settings)


def mark_client_submission_pending(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    postgres_database.mark_client_submission_pending(client_id, settings=settings)


def mark_client_submission_intent(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    postgres_database.mark_client_submission_intent(client_id, settings=settings)


def clear_client_submission_state(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    postgres_database.clear_client_submission_state(client_id, settings=settings)


def client_submission_age_seconds(
    client_id: str,
    *,
    settings: Settings | None = None,
) -> int | None:
    return postgres_database.client_submission_age_seconds(client_id, settings=settings)


def set_client_active(client_id: str, active: bool, *, settings: Settings | None = None) -> None:
    postgres_database.set_client_active(client_id, active, settings=settings)


def mark_client_done(
    client_id: str,
    *,
    status: str = "registered",
    settings: Settings | None = None,
) -> None:
    postgres_database.mark_client_done(client_id, status=status, settings=settings)


def update_client_state(
    client_id: str,
    *,
    status: str,
    message: str,
    exit_code: int,
    backoff_seconds: int | None = None,
    settings: Settings | None = None,
) -> None:
    postgres_database.update_client_state(
        client_id,
        status=status,
        message=message,
        exit_code=exit_code,
        backoff_seconds=backoff_seconds,
        settings=settings,
    )


def create_run_record(
    settings: Settings | None,
    record: RunRecord,
    screenshot_paths: Iterable[str],
) -> None:
    postgres_database.create_run_record(settings, record, screenshot_paths)


def list_runs(
    *,
    limit: int = 50,
    offset: int = 0,
    client_id: str | None = None,
    status: str | None = None,
    settings: Settings | None = None,
) -> list[RunSummary]:
    return postgres_database.list_runs(
        limit=limit,
        offset=offset,
        client_id=client_id,
        status=status,
        settings=settings,
    )


def get_run(
    run_id: str,
    *,
    settings: Settings | None = None,
) -> RunDetail | None:
    return postgres_database.get_run(run_id, settings=settings)


def get_worker_state(settings: Settings | None = None) -> WorkerState:
    return postgres_database.get_worker_state(settings)


def update_worker_state(
    settings: Settings | None = None,
    *,
    expected_owner_token: str | None = None,
    **changes: object,
) -> WorkerState:
    return postgres_database.update_worker_state(
        settings,
        expected_owner_token=expected_owner_token,
        **changes,
    )


def cleanup_database_history(
    settings: Settings | None = None,
) -> None:
    postgres_database.cleanup_database_history(settings)


def using_postgres(settings: Settings | None = None) -> bool:
    return bool(_settings(settings).database_url)


def _settings(settings: Settings | None) -> Settings:
    return settings or load_settings(require_login=False)
