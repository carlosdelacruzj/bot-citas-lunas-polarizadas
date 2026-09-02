from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from psycopg import Connection

from appointment_bot.config import Settings, load_settings
from appointment_bot.core.credential_cipher import CredentialCipher
from appointment_bot.core.documents import normalize_document_type
from appointment_bot.core.models import ServiceOrderCreateResult
from appointment_bot.core.service_packages import (
    STANDARD_TOTAL_AMOUNT,
    infer_service_package,
    normalize_service_package,
    validate_service_package_terms,
)
from appointment_bot.db.common import (
    _parse_allowed_weekdays,
    _parse_excluded_date_ranges,
    _parse_maximum_reservation_date,
    _parse_minimum_reservation_date,
)
from appointment_bot.db.service_order_repository import (
    ServiceOrderPersistenceRequest,
    persist_service_order,
)
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
        persistence_request = _prepare_persistence_request(request, resolved_settings)
        with self._unit_of_work_factory(resolved_settings, connection_override) as connection:
            return self._repository(
                persistence_request,
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


def _prepare_persistence_request(
    request: CreateServiceOrderRequest,
    settings: Settings,
) -> ServiceOrderPersistenceRequest:
    document_number = request.document_number.strip()
    if not document_number:
        raise ValueError("document_number is required.")
    if not request.password:
        raise ValueError("password is required.")
    if request.priority < 0:
        raise ValueError("priority must be non-negative.")

    service_type = request.service_type.strip().lower()
    if service_type not in {"standard", "selected_weekday", "custom"}:
        raise ValueError("service_type must be standard, selected_weekday or custom.")
    reservation_price = (
        STANDARD_TOTAL_AMOUNT
        if request.reservation_price is None
        else request.reservation_price
    )
    if reservation_price <= 0:
        raise ValueError("reservation_price must be greater than zero.")
    service_package = normalize_service_package(
        request.service_package or infer_service_package(service_type)
    )
    official_fee_amount, initial_payment_amount = validate_service_package_terms(
        service_package,
        service_type,
        reservation_price,
        charge_required=request.charge_required,
    )
    if request.minimum_reservation_hour is not None:
        raise ValueError("Las restricciones horarias ya no se aceptan.")
    minimum_date = _parse_minimum_reservation_date(request.minimum_reservation_date)
    maximum_date = _parse_maximum_reservation_date(request.maximum_reservation_date)
    allowed_weekdays = _parse_allowed_weekdays(request.allowed_weekdays)
    if service_type == "selected_weekday" and (
        allowed_weekdays is None or len(allowed_weekdays) != 1
    ):
        raise ValueError("selected_weekday requires exactly one allowed weekday.")
    if minimum_date is not None and maximum_date is not None and maximum_date < minimum_date:
        raise ValueError("maximum_reservation_date cannot be before minimum_reservation_date.")

    return ServiceOrderPersistenceRequest(
        document_number=document_number,
        encrypted_password=CredentialCipher(settings.credential_encryption_keys).encrypt(
            request.password
        ),
        document_type=normalize_document_type(request.document_type),
        priority=request.priority,
        contact_whatsapp=request.contact_whatsapp,
        contact_whatsapp_username=request.contact_whatsapp_username,
        contact_name=request.contact_name,
        contact_source=request.contact_source,
        applicant_name=request.applicant_name,
        charge_required=request.charge_required,
        service_type=service_type,
        service_package=service_package,
        reservation_price=reservation_price,
        official_fee_amount=official_fee_amount,
        initial_payment_amount=initial_payment_amount,
        minimum_date=minimum_date,
        maximum_date=maximum_date,
        allowed_weekdays=allowed_weekdays,
        excluded_date_ranges=_parse_excluded_date_ranges(request.excluded_date_ranges),
        parent_order_id=_optional_clean_text(request.parent_order_id),
        program_expediente=_optional_clean_text(request.program_expediente),
        program_plate=_optional_clean_text(request.program_plate),
        actor=" ".join(request.actor.split())[:120] or "system",
        require_preflight=request.require_preflight,
        occurred_at=datetime.now(UTC).isoformat(timespec="microseconds"),
    )


def _optional_clean_text(value: object) -> str | None:
    if value in {None, ""}:
        return None
    text = " ".join(str(value).split())
    return text or None
