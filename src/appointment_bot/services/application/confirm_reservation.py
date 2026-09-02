from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from psycopg import Connection

from appointment_bot.config import Settings, load_settings
from appointment_bot.core.models import RunRecord
from appointment_bot.core.rules import parse_appointment_date
from appointment_bot.core.statuses import sanitize_details
from appointment_bot.db.orders import _update_applicant_name_for_order
from appointment_bot.db.reservation_repository import (
    PostgresReservationRepository,
    ReservationOrderState,
)
from appointment_bot.db.runs import create_run_record
from appointment_bot.db.unit_of_work import postgres_unit_of_work
from appointment_bot.db.whatsapp_messages import archive_whatsapp_evidence
from appointment_bot.services.detail_helpers import appointment_datetime_details

UnitOfWorkFactory = Callable[
    [Settings, Connection | None],
    AbstractContextManager[Connection],
]


class ReservationRepository(Protocol):
    def get_order(
        self,
        connection: Connection,
        order_id: str,
    ) -> ReservationOrderState | None: ...

    def save_reservation(self, connection: Connection, **values: Any) -> str: ...

    def ensure_pending_payment(self, connection: Connection, **values: Any) -> None: ...

    def update_order_after_confirmation(
        self,
        connection: Connection,
        **values: Any,
    ) -> None: ...


@dataclass(frozen=True, slots=True, repr=False)
class ConfirmReservationRequest:
    order_id: str
    report: object
    confirmed: bool | None = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class ConfirmReservation:
    def __init__(
        self,
        *,
        repository: ReservationRepository | None = None,
        unit_of_work_factory: UnitOfWorkFactory = postgres_unit_of_work,
        evidence_archiver=archive_whatsapp_evidence,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository or PostgresReservationRepository()
        self._unit_of_work_factory = unit_of_work_factory
        self._evidence_archiver = evidence_archiver
        self._clock = clock or _utc_now

    def execute(
        self,
        request: ConfirmReservationRequest,
        *,
        settings: Settings | None = None,
        connection_override: Connection | None = None,
    ) -> bool:
        resolved_settings = settings or load_settings(require_login=False)
        details = getattr(request.report, "details", None) or {}
        run_id = getattr(request.report, "run_id", None)
        is_confirmed = (
            bool(getattr(request.report, "reservation_confirmed", False))
            if request.confirmed is None
            else request.confirmed
        )
        appointment_date_raw, appointment_hour_raw = appointment_datetime_details(details)
        appointment_date = _optional_text(appointment_date_raw)
        appointment_day = (
            parse_appointment_date(appointment_date) if appointment_date is not None else None
        )
        appointment_hour = _optional_text(appointment_hour_raw)
        status = "confirmed" if is_confirmed else "unconfirmed"
        occurred_at = self._clock()

        with self._unit_of_work_factory(resolved_settings, connection_override) as connection:
            order = self._repository.get_order(connection, request.order_id)
            if order is None:
                return False

            program_expediente = (
                _detail_text(details, "program_expediente") or order.program_expediente
            )
            program_plate = _detail_text(details, "program_plate") or order.program_plate
            evidence_path = getattr(request.report, "screenshot_path", None)
            if is_confirmed:
                archived = self._evidence_archiver(
                    request.order_id,
                    [
                        *(getattr(request.report, "screenshot_paths", None) or []),
                        evidence_path,
                    ],
                )
                if archived is not None:
                    evidence_path = str(archived)

            reservation_id = self._repository.save_reservation(
                connection,
                order_id=request.order_id,
                run_id=run_id,
                status=status,
                site=_detail_text(details, "sede"),
                appointment_date=appointment_date,
                appointment_day=appointment_day,
                appointment_hour=appointment_hour,
                slots=_detail_text(details, "cupos"),
                evidence_path=evidence_path,
                details=sanitize_details(details) if details else None,
                program_expediente=program_expediente,
                program_plate=program_plate,
                occurred_at=occurred_at,
            )
            if not is_confirmed:
                return True

            no_charge = not order.charge_required
            if not no_charge:
                self._repository.ensure_pending_payment(
                    connection,
                    order_id=request.order_id,
                    reservation_id=reservation_id,
                    amount_agreed=order.reservation_price,
                    occurred_at=occurred_at,
                )
            self._repository.update_order_after_confirmation(
                connection,
                order_id=request.order_id,
                no_charge=no_charge,
                program_expediente=program_expediente,
                program_plate=program_plate,
                occurred_at=occurred_at,
            )
            return True


_DEFAULT_USE_CASE = ConfirmReservation()


def record_reservation_for_order(
    order_id: str,
    report: object,
    *,
    confirmed: bool | None = None,
    settings: Settings | None = None,
    _connection_override: Connection | None = None,
) -> None:
    _DEFAULT_USE_CASE.execute(
        ConfirmReservationRequest(
            order_id=order_id,
            report=report,
            confirmed=confirmed,
        ),
        settings=settings,
        connection_override=_connection_override,
    )


def record_run_outcome(
    settings: Settings | None,
    record: RunRecord,
    screenshot_paths: Iterable[str],
    *,
    report: object,
    person_name: str | None,
    include_reservation: bool,
) -> None:
    """Persist a run and its domain effects in one transaction."""
    resolved_settings = settings or load_settings(require_login=False)
    with postgres_unit_of_work(resolved_settings) as connection:
        create_run_record(
            resolved_settings,
            record,
            screenshot_paths,
            _connection_override=connection,
        )
        if record.order_id and person_name:
            _update_applicant_name_for_order(
                record.order_id,
                person_name,
                settings=resolved_settings,
                _connection_override=connection,
            )
        if record.order_id and include_reservation:
            record_reservation_for_order(
                record.order_id,
                report,
                confirmed=True,
                settings=resolved_settings,
                _connection_override=connection,
            )


def _detail_text(details: dict[str, Any], key: str) -> str | None:
    return _optional_text(details.get(key))


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
