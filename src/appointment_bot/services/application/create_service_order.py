from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal

from psycopg import Connection

from appointment_bot.config import Settings, load_settings
from appointment_bot.core.models import ServiceOrderCreateResult
from appointment_bot.db.service_order_repository import persist_service_order
from appointment_bot.db.unit_of_work import postgres_unit_of_work

ServiceOrderRepository = Callable[..., ServiceOrderCreateResult]
UnitOfWorkFactory = Callable[
    [Settings, Connection | None],
    AbstractContextManager[Connection],
]


@dataclass(frozen=True, slots=True, repr=False)
class CreateServiceOrderRequest:
    document_number: str
    password: str
    document_type: str = "dni"
    priority: int = 0
    contact_whatsapp: str | None = None
    contact_whatsapp_username: str | None = None
    contact_name: str | None = None
    contact_source: str | None = None
    applicant_name: str | None = None
    charge_required: bool = True
    service_type: str = "standard"
    service_package: str | None = None
    reservation_price: Decimal | None = None
    minimum_reservation_hour: int | None = None
    minimum_reservation_date: str | date | None = None
    maximum_reservation_date: str | date | None = None
    allowed_weekdays: Iterable[int] | None = None
    excluded_date_ranges: Iterable[dict[str, object] | Iterable[object]] | None = None
    parent_order_id: str | None = None
    program_expediente: str | None = None
    program_plate: str | None = None
    actor: str = "system"
    require_preflight: bool = True


class CreateServiceOrder:
    def __init__(
        self,
        *,
        repository: ServiceOrderRepository = persist_service_order,
        unit_of_work_factory: UnitOfWorkFactory = postgres_unit_of_work,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def execute(
        self,
        request: CreateServiceOrderRequest,
        *,
        settings: Settings | None = None,
        connection_override: Connection | None = None,
    ) -> ServiceOrderCreateResult:
        resolved_settings = settings or load_settings(require_login=False)
        values = {field.name: getattr(request, field.name) for field in fields(request)}
        with self._unit_of_work_factory(resolved_settings, connection_override) as connection:
            return self._repository(
                **values,
                settings=resolved_settings,
                _connection_override=connection,
            )


_DEFAULT_USE_CASE = CreateServiceOrder()


def create_service_order(
    *,
    document_number: str,
    password: str,
    document_type: str = "dni",
    priority: int = 0,
    contact_whatsapp: str | None = None,
    contact_whatsapp_username: str | None = None,
    contact_name: str | None = None,
    contact_source: str | None = None,
    applicant_name: str | None = None,
    charge_required: bool = True,
    service_type: str = "standard",
    service_package: str | None = None,
    reservation_price: Decimal | None = None,
    minimum_reservation_hour: int | None = None,
    minimum_reservation_date: str | date | None = None,
    maximum_reservation_date: str | date | None = None,
    allowed_weekdays: Iterable[int] | None = None,
    excluded_date_ranges: Iterable[dict[str, object] | Iterable[object]] | None = None,
    parent_order_id: str | None = None,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    actor: str = "system",
    require_preflight: bool = True,
    settings: Settings | None = None,
    _connection_override: Connection | None = None,
) -> ServiceOrderCreateResult:
    request = CreateServiceOrderRequest(
        document_number=document_number,
        password=password,
        document_type=document_type,
        priority=priority,
        contact_whatsapp=contact_whatsapp,
        contact_whatsapp_username=contact_whatsapp_username,
        contact_name=contact_name,
        contact_source=contact_source,
        applicant_name=applicant_name,
        charge_required=charge_required,
        service_type=service_type,
        service_package=service_package,
        reservation_price=reservation_price,
        minimum_reservation_hour=minimum_reservation_hour,
        minimum_reservation_date=minimum_reservation_date,
        maximum_reservation_date=maximum_reservation_date,
        allowed_weekdays=allowed_weekdays,
        excluded_date_ranges=excluded_date_ranges,
        parent_order_id=parent_order_id,
        program_expediente=program_expediente,
        program_plate=program_plate,
        actor=actor,
        require_preflight=require_preflight,
    )
    return _DEFAULT_USE_CASE.execute(
        request,
        settings=settings,
        connection_override=_connection_override,
    )
