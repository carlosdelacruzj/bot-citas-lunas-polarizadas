from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Client:
    client_id: str
    name: str
    username: str
    password: str
    priority: int
    active: bool
    done: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ClientSummary:
    client_id: str
    name: str
    username_masked: str
    priority: int
    active: bool
    done: bool
    created_at: str
    updated_at: str
    last_status: str | None
    last_message: str | None
    consecutive_errors: int
    next_allowed_at: str | None
    last_run_at: str | None
    last_success_at: str | None
    programmed_at: str | None


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    client_id: str | None
    status: str
    message: str
    exit_code: int
    started_at: str
    finished_at: str
    duration_seconds: float
    reservation_attempted: bool
    reservation_confirmed: bool
    details: dict[str, Any] | None
    screenshot_path: str | None


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    client_id: str | None
    status: str
    message: str
    exit_code: int
    started_at: str
    finished_at: str
    duration_seconds: float
    reservation_attempted: bool
    reservation_confirmed: bool
    screenshot_path: str | None
    screenshot_count: int
    created_at: str


@dataclass(frozen=True)
class RunDetail(RunSummary):
    details: dict[str, Any] | None
    screenshot_paths: list[str]


@dataclass(frozen=True)
class WorkerState:
    phase: str = "stopped"
    paused: bool = False
    current_client_id: str | None = None
    masked_account: str | None = None
    session_started_at: str | None = None
    last_check_at: str | None = None
    next_check_at: str | None = None
    confirmed_reservations: int = 0
    consecutive_errors: int = 0
    last_error: str | None = None
    availability_signature: str | None = None
    owner_token: str | None = None
    updated_at: str | None = None
