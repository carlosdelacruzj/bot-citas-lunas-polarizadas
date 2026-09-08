from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

SERVICE_PACKAGE_STANDARD = "standard"
SERVICE_PACKAGE_RESTRICTED = "restricted"
SERVICE_PACKAGE_INTEGRAL = "integral"
SERVICE_PACKAGE_CUSTOM = "custom"

SERVICE_TYPE_STANDARD = "standard"
SERVICE_TYPE_SELECTED_WEEKDAY = "selected_weekday"
SERVICE_TYPE_CUSTOM = "custom"
SERVICE_TYPES = frozenset(
    {
        SERVICE_TYPE_STANDARD,
        SERVICE_TYPE_SELECTED_WEEKDAY,
        SERVICE_TYPE_CUSTOM,
    }
)

STANDARD_TOTAL_AMOUNT = Decimal("50.00")
RESTRICTED_TOTAL_AMOUNT = Decimal("70.00")
INTEGRAL_TOTAL_AMOUNT = Decimal("160.00")
INTEGRAL_INITIAL_PAYMENT = Decimal("80.00")
INTEGRAL_OFFICIAL_FEE = Decimal("71.40")
ZERO_AMOUNT = Decimal("0.00")
DEFAULT_RESERVATION_PRICE_TEXT = f"{STANDARD_TOTAL_AMOUNT:.2f}"


@dataclass(frozen=True)
class ServicePackageDefinition:
    key: str
    label: str
    total_amount: Decimal | None
    initial_payment_amount: Decimal
    official_fee_amount: Decimal
    default_service_type: str
    compatible_service_types: frozenset[str]
    requires_restrictions: bool = False

    @property
    def balance_amount(self) -> Decimal | None:
        if self.total_amount is None:
            return None
        return self.total_amount - self.initial_payment_amount

    @property
    def management_fee_amount(self) -> Decimal | None:
        if self.total_amount is None:
            return None
        return self.total_amount - self.official_fee_amount

    @property
    def fixed_price(self) -> bool:
        return self.total_amount is not None

    def public_payload(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "total_amount": money_text(self.total_amount),
            "initial_payment_amount": money_text(self.initial_payment_amount),
            "official_fee_amount": money_text(self.official_fee_amount),
            "balance_amount": money_text(self.balance_amount),
            "management_fee_amount": money_text(self.management_fee_amount),
            "fixed_price": self.fixed_price,
            "default_service_type": self.default_service_type,
            "compatible_service_types": sorted(self.compatible_service_types),
            "requires_restrictions": self.requires_restrictions,
        }


SERVICE_PACKAGE_CATALOG: dict[str, ServicePackageDefinition] = {
    SERVICE_PACKAGE_STANDARD: ServicePackageDefinition(
        key=SERVICE_PACKAGE_STANDARD,
        label="Servicio regular",
        total_amount=STANDARD_TOTAL_AMOUNT,
        initial_payment_amount=ZERO_AMOUNT,
        official_fee_amount=ZERO_AMOUNT,
        default_service_type=SERVICE_TYPE_STANDARD,
        compatible_service_types=frozenset({SERVICE_TYPE_STANDARD}),
    ),
    SERVICE_PACKAGE_RESTRICTED: ServicePackageDefinition(
        key=SERVICE_PACKAGE_RESTRICTED,
        label="Disponibilidad restringida",
        total_amount=RESTRICTED_TOTAL_AMOUNT,
        initial_payment_amount=ZERO_AMOUNT,
        official_fee_amount=ZERO_AMOUNT,
        default_service_type=SERVICE_TYPE_CUSTOM,
        compatible_service_types=frozenset(
            {SERVICE_TYPE_SELECTED_WEEKDAY, SERVICE_TYPE_CUSTOM}
        ),
        requires_restrictions=True,
    ),
    SERVICE_PACKAGE_INTEGRAL: ServicePackageDefinition(
        key=SERVICE_PACKAGE_INTEGRAL,
        label="Trámite integral",
        total_amount=INTEGRAL_TOTAL_AMOUNT,
        initial_payment_amount=INTEGRAL_INITIAL_PAYMENT,
        official_fee_amount=INTEGRAL_OFFICIAL_FEE,
        default_service_type=SERVICE_TYPE_STANDARD,
        compatible_service_types=frozenset({SERVICE_TYPE_STANDARD}),
    ),
    SERVICE_PACKAGE_CUSTOM: ServicePackageDefinition(
        key=SERVICE_PACKAGE_CUSTOM,
        label="Monto personalizado",
        total_amount=None,
        initial_payment_amount=ZERO_AMOUNT,
        official_fee_amount=ZERO_AMOUNT,
        default_service_type=SERVICE_TYPE_CUSTOM,
        compatible_service_types=SERVICE_TYPES,
    ),
}
SERVICE_PACKAGES = frozenset(SERVICE_PACKAGE_CATALOG)


def service_package_definition(value: str | None) -> ServicePackageDefinition:
    return SERVICE_PACKAGE_CATALOG[normalize_service_package(value)]


def service_package_catalog_payload() -> dict[str, object]:
    return {
        "default_package": SERVICE_PACKAGE_STANDARD,
        "service_packages": [
            definition.public_payload()
            for definition in SERVICE_PACKAGE_CATALOG.values()
        ],
    }


def normalize_service_package(value: str | None) -> str:
    package = (value or SERVICE_PACKAGE_STANDARD).strip().lower()
    if package not in SERVICE_PACKAGES:
        raise ValueError("service_package must be standard, restricted, integral or custom.")
    return package


def infer_service_package(service_type: str) -> str:
    return {
        SERVICE_TYPE_SELECTED_WEEKDAY: SERVICE_PACKAGE_RESTRICTED,
        SERVICE_TYPE_CUSTOM: SERVICE_PACKAGE_CUSTOM,
    }.get(service_type, SERVICE_PACKAGE_STANDARD)


def validate_service_package_compatibility(
    service_package: str,
    service_type: str,
) -> None:
    definition = service_package_definition(service_package)
    if service_type not in definition.compatible_service_types:
        compatible = ", ".join(sorted(definition.compatible_service_types))
        raise ValueError(
            f"service_package {definition.key} is not compatible with service_type "
            f"{service_type}; expected one of: {compatible}."
        )


def package_amounts(
    service_package: str,
    reservation_price: Decimal,
) -> tuple[Decimal, Decimal]:
    definition = service_package_definition(service_package)
    if definition.fixed_price and reservation_price != definition.total_amount:
        raise ValueError(
            f"El paquete {definition.label} tiene un precio fijo de "
            f"S/{money_text(definition.total_amount)}."
        )
    return definition.official_fee_amount, definition.initial_payment_amount


def validate_service_package_terms(
    service_package: str,
    service_type: str,
    reservation_price: Decimal,
    *,
    charge_required: bool,
) -> tuple[Decimal, Decimal]:
    validate_service_package_compatibility(service_package, service_type)
    official_fee_amount, initial_payment_amount = package_amounts(
        service_package,
        reservation_price,
    )
    if service_package == SERVICE_PACKAGE_INTEGRAL and not charge_required:
        raise ValueError("El paquete Trámite integral exige charge_required=true.")
    return official_fee_amount, initial_payment_amount


def validate_integral_payment_totals(
    service_package: str,
    *,
    amount_agreed: Decimal,
    amount_paid: Decimal,
    complete: bool,
) -> None:
    if service_package != SERVICE_PACKAGE_INTEGRAL:
        return
    if amount_agreed != INTEGRAL_TOTAL_AMOUNT:
        raise ValueError("El paquete Trámite integral exige un monto acordado de S/160.00.")
    if amount_paid < INTEGRAL_INITIAL_PAYMENT:
        raise ValueError("El paquete Trámite integral ya registra un abono inicial de S/80.00.")
    if complete and amount_paid != INTEGRAL_TOTAL_AMOUNT:
        raise ValueError("El pago completo del paquete Trámite integral debe acumular S/160.00.")


def service_package_label(
    service_package: str | None,
    service_type: str | None = None,
) -> str:
    if service_package:
        return service_package_definition(service_package).label
    inferred = infer_service_package(service_type or SERVICE_TYPE_STANDARD)
    return service_package_definition(inferred).label


def money_text(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


__all__ = [
    "DEFAULT_RESERVATION_PRICE_TEXT",
    "INTEGRAL_INITIAL_PAYMENT",
    "INTEGRAL_OFFICIAL_FEE",
    "INTEGRAL_TOTAL_AMOUNT",
    "RESTRICTED_TOTAL_AMOUNT",
    "SERVICE_PACKAGE_CATALOG",
    "SERVICE_PACKAGE_CUSTOM",
    "SERVICE_PACKAGE_INTEGRAL",
    "SERVICE_PACKAGE_RESTRICTED",
    "SERVICE_PACKAGE_STANDARD",
    "SERVICE_PACKAGES",
    "SERVICE_TYPES",
    "STANDARD_TOTAL_AMOUNT",
    "ServicePackageDefinition",
    "infer_service_package",
    "money_text",
    "normalize_service_package",
    "package_amounts",
    "service_package_catalog_payload",
    "service_package_definition",
    "service_package_label",
    "validate_integral_payment_totals",
    "validate_service_package_compatibility",
    "validate_service_package_terms",
]
