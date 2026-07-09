from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ServiceOrderCandidate:
    order_id: str
    name: str
    username: str
    priority: int
    status: str
    created_at: str
    updated_at: str
    contact_name: str | None = None

    @property
    def notification_name(self) -> str:
        parts = []
        if self.name and self.name != self.username:
            parts.append(self.name)
        if self.contact_name:
            parts.append(f"Contacto: {self.contact_name}")
        return " | ".join(parts) or self.order_id


@dataclass(frozen=True)
class ServiceOrderRuntime:
    order_id: str
    name: str
    username: str
    password: str
    priority: int
    status: str
    created_at: str
    updated_at: str
    contact_name: str | None = None

    @property
    def notification_name(self) -> str:
        parts = []
        if self.name and self.name != self.username:
            parts.append(self.name)
        if self.contact_name:
            parts.append(f"Contacto: {self.contact_name}")
        return " | ".join(parts) or self.order_id


@dataclass(frozen=True)
class ServiceOrderSummary:
    order_id: str
    applicant_id: str
    applicant_name: str | None
    document_number_masked: str
    contact_name: str | None
    contact_whatsapp_masked: str | None
    contact_source: str | None
    priority: int
    charge_required: bool
    status: str
    reservation_status: str | None
    reservation_site: str | None
    reservation_date: str | None
    reservation_hour: str | None
    payment_status: str | None
    amount_agreed: str | None
    amount_paid: str | None
    minimum_reservation_hour: int | None
    minimum_reservation_date: str | None
    allowed_weekdays: tuple[int, ...] | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ServiceOrderCreateResult:
    order_id: str
    applicant_id: str
    portal_account_id: str
    contact_id: str | None


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    order_id: str | None
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
    order_id: str | None
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
    current_order_id: str | None = None
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


@dataclass(frozen=True)
class WorkerCommand:
    command_id: str
    command: str
    status: str
    requested_by: str | None
    worker_owner_token: str | None
    requested_at: str
    claimed_at: str | None
    processed_at: str | None
    error_message: str | None
