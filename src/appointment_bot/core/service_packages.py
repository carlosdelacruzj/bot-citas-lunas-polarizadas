from __future__ import annotations

from decimal import Decimal

SERVICE_PACKAGE_STANDARD = "standard"
SERVICE_PACKAGE_RESTRICTED = "restricted"
SERVICE_PACKAGE_INTEGRAL = "integral"
SERVICE_PACKAGE_CUSTOM = "custom"

SERVICE_PACKAGES = {
    SERVICE_PACKAGE_STANDARD,
    SERVICE_PACKAGE_RESTRICTED,
    SERVICE_PACKAGE_INTEGRAL,
    SERVICE_PACKAGE_CUSTOM,
}

INTEGRAL_TOTAL_AMOUNT = Decimal("160.00")
INTEGRAL_INITIAL_PAYMENT = Decimal("80.00")
INTEGRAL_OFFICIAL_FEE = Decimal("71.40")
INTEGRAL_MANAGEMENT_FEE = INTEGRAL_TOTAL_AMOUNT - INTEGRAL_OFFICIAL_FEE


def normalize_service_package(value: str | None) -> str:
    package = (value or SERVICE_PACKAGE_STANDARD).strip().lower()
    if package not in SERVICE_PACKAGES:
        raise ValueError("service_package must be standard, restricted, integral or custom.")
    return package


def infer_service_package(service_type: str) -> str:
    return {
        "selected_weekday": SERVICE_PACKAGE_RESTRICTED,
        "custom": SERVICE_PACKAGE_CUSTOM,
    }.get(service_type, SERVICE_PACKAGE_STANDARD)


def package_amounts(
    service_package: str,
    reservation_price: Decimal,
) -> tuple[Decimal, Decimal]:
    if service_package == SERVICE_PACKAGE_INTEGRAL:
        if reservation_price != INTEGRAL_TOTAL_AMOUNT:
            raise ValueError("El paquete integral tiene un precio fijo de S/160.00.")
        return INTEGRAL_OFFICIAL_FEE, INTEGRAL_INITIAL_PAYMENT
    return Decimal("0.00"), Decimal("0.00")
