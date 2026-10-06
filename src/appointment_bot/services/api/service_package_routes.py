from __future__ import annotations

from http import HTTPStatus

from appointment_bot.core.service_packages import service_package_catalog_payload


def service_packages_payload() -> tuple[HTTPStatus, dict[str, object]]:
    return HTTPStatus.OK, service_package_catalog_payload()


__all__ = ["service_packages_payload"]
