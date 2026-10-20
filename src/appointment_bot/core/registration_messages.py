from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from appointment_bot.core.service_packages import (
    DEFAULT_RESERVATION_PRICE_TEXT,
    SERVICE_PACKAGE_STANDARD,
    service_package_label,
)


def _monitoring_started_context(
    *,
    display_name: str | None,
    service_type: str,
    service_package: str,
    reservation_price: str,
    minimum_reservation_date: str | None,
    maximum_reservation_date: str | None,
    allowed_weekdays: tuple[int, ...] | None,
    excluded_date_ranges: tuple[dict[str, str], ...],
) -> dict[str, str]:
    name = " ".join((display_name or "").split())
    if not name:
        raise ValueError("El aviso de registro validado requiere el nombre del solicitante.")
    exclusions = _excluded_dates_text(excluded_date_ranges)
    return {
        "nombre": name,
        "servicio": _service_label(service_type, service_package),
        "monto": str(reservation_price or DEFAULT_RESERVATION_PRICE_TEXT),
        "condiciones": _search_conditions_text(
            minimum_reservation_date,
            maximum_reservation_date,
            allowed_weekdays,
        ),
        "fechas_excluidas": f"Fechas excluidas: {exclusions}" if exclusions else "",
    }


def _registration_name_context(display_name: str | None) -> dict[str, str]:
    name = " ".join((display_name or "").split())
    if not name:
        raise ValueError("El aviso de registro requiere un nombre para el saludo.")
    return {"nombre": name}


def _service_label(
    service_type: str,
    service_package: str = SERVICE_PACKAGE_STANDARD,
) -> str:
    return service_package_label(service_package, service_type)


def _weekday_name(value: int) -> str:
    return {
        1: "los lunes",
        2: "los martes",
        3: "los miércoles",
        4: "los jueves",
        5: "los viernes",
        6: "los sábados",
        7: "los domingos",
    }.get(int(value), "el día indicado")


def _search_conditions_text(
    minimum_date: str | None,
    maximum_date: str | None,
    allowed_weekdays: tuple[int, ...] | None,
) -> str:
    conditions = []
    if allowed_weekdays:
        weekday_names = [_weekday_name(day) for day in allowed_weekdays]
        if len(weekday_names) == 1:
            conditions.append(f"Solo {weekday_names[0]}")
        else:
            conditions.append("Días permitidos: " + ", ".join(weekday_names))
    if minimum_date and maximum_date:
        conditions.append(
            f"desde el {_display_date(minimum_date)} hasta el {_display_date(maximum_date)}"
        )
    elif minimum_date:
        conditions.append(f"a partir del {_display_date(minimum_date)}")
    elif maximum_date:
        conditions.append(f"hasta el {_display_date(maximum_date)}")
    if not conditions:
        return "Cualquier fecha disponible."
    return ", ".join(conditions) + "."


def _excluded_dates_text(excluded_date_ranges: tuple[dict[str, str], ...]) -> str:
    values = []
    for item in excluded_date_ranges:
        start = str(item.get("start_date") or "")
        end = str(item.get("end_date") or "")
        if not start or not end:
            continue
        if start == end:
            values.append(_display_date(start))
        else:
            values.append(f"{_display_date(start)} al {_display_date(end)}")
    return "; ".join(values)


def _display_date(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    except ValueError:
        return value



def program_registration_context(
    name: str,
    programs: list[dict[str, Any]],
    specs: dict[str, dict[str, Any]],
) -> dict[str, str]:
    services = []
    groups: dict[str, list[str]] = {}
    total = Decimal("0")
    for index, row in enumerate(programs, 1):
        expediente = str(row.get("expediente") or "sin expediente")
        plate = str(row.get("placa") or "sin placa")
        spec = specs[expediente]
        context = _monitoring_started_context(
            display_name=name,
            service_type=spec["service_type"],
            service_package=spec["service_package"],
            reservation_price=str(spec["reservation_price"]),
            minimum_reservation_date=(str(spec["minimum_reservation_date"])
                                      if spec.get("minimum_reservation_date") else None),
            maximum_reservation_date=(str(spec["maximum_reservation_date"])
                                      if spec.get("maximum_reservation_date") else None),
            allowed_weekdays=spec.get("allowed_weekdays"),
            excluded_date_ranges=spec.get("excluded_date_ranges") or (),
        )
        amount = Decimal(str(spec["reservation_price"]))
        if spec["charge_required"]:
            total += amount
            price = f"S/{amount:.2f}"
        else:
            price = "Sin cobro adicional"
        conditions = context["condiciones"]
        if context["fechas_excluidas"]:
            conditions += "\n" + context["fechas_excluidas"]
        groups.setdefault(conditions, []).append(expediente)
        services.append(
            f"{index}. Placa {plate} · Expediente {expediente}\n"
            f"   {context['servicio']}: {price}"
        )
        if len(programs) == 1:
            service = context["servicio"]
            if service == "Servicio regular":
                service = "Regular"
            return {**context, "servicio": service, "placa": plate,
                    "expediente": expediente, "precio": price}
    if not programs:
        raise ValueError("El aviso de registro requiere al menos un trámite.")
    shared_conditions = len(groups) == 1
    if not shared_conditions:
        for index, row in enumerate(programs):
            conditions = next(text for text, ids in groups.items() if str(row['expediente']) in ids)
            services[index] += "\n   Disponibilidad: " + conditions
    return {
        "nombre": name,
        "tramites": "\n\n".join(services),
        "precio": f"S/{total:.2f}" if total else "Sin cobro adicional",
        "disponibilidad": (
            "Disponibilidad para todos: " + next(iter(groups)) if shared_conditions else ""
        ),
    }
