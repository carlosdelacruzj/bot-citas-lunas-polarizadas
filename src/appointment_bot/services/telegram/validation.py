from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _valid_order_id(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) is not None


def _money_value(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        amount = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() else None


def _validated_payment_amount(value: Any) -> Decimal:
    amount = _money_value(value)
    if amount is None or amount <= 0 or amount > Decimal("99999.99"):
        raise ValueError("El monto total debe ser mayor que cero y menor que S/100000.")
    if amount.as_tuple().exponent < -2:
        raise ValueError("El monto total admite como maximo dos decimales.")
    return amount.quantize(Decimal("0.01"))


def _payment_balance(order: dict[str, Any]) -> Decimal:
    agreed = _money_value(order.get("amount_agreed")) or Decimal("0")
    paid = _money_value(order.get("amount_paid")) or Decimal("0")
    return max(agreed - paid, Decimal("0"))


def _parse_single_weekday(value: str) -> int:
    normalized = unicodedata.normalize("NFKD", value.strip().casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    weekdays = {
        "1": 1,
        "lunes": 1,
        "2": 2,
        "martes": 2,
        "3": 3,
        "miercoles": 3,
        "4": 4,
        "jueves": 4,
        "5": 5,
        "viernes": 5,
        "6": 6,
        "sabado": 6,
        "7": 7,
        "domingo": 7,
    }
    weekday = weekdays.get(normalized)
    if weekday is None:
        raise ValueError("Elige un dia entre lunes y domingo.")
    return weekday


def _parse_rules_step(
    step: int,
    text: str,
    current: dict[str, Any],
) -> tuple[str, Any]:
    value = text.strip().lower()
    fields = (
        "minimum_reservation_date",
        "maximum_reservation_date",
        "allowed_weekdays",
        "excluded_date_ranges",
    )
    field = fields[step]
    if value in {"igual", "mantener"}:
        return field, current.get(field)
    if value in {"quitar", "ninguno", "todos"}:
        return field, [] if field == "excluded_date_ranges" else None
    if step in {0, 1}:
        try:
            parsed = datetime.strptime(value, "%d-%m-%Y").date()
        except ValueError as exc:
            raise ValueError("Usa DD-MM-YYYY, igual o quitar.") from exc
        return field, parsed.isoformat()
    if step == 3:
        ranges = []
        for item in value.split(";"):
            item = item.strip()
            match = re.fullmatch(
                r"(\d{2}-\d{2}-\d{4})(?:\s+(?:a|al|hasta)\s+"
                r"(\d{2}-\d{2}-\d{4}))?",
                item,
            )
            if match is None:
                raise ValueError(
                    "Usa DD-MM-YYYY o DD-MM-YYYY al DD-MM-YYYY; separa varios con ;"
                )
            try:
                start = datetime.strptime(match.group(1), "%d-%m-%Y").date()
                end = datetime.strptime(
                    match.group(2) or match.group(1),
                    "%d-%m-%Y",
                ).date()
            except ValueError as exc:
                raise ValueError("Una de las fechas excluidas no es valida.") from exc
            if end < start:
                raise ValueError("Una fecha excluida no puede terminar antes de comenzar.")
            ranges.append({"start_date": start.isoformat(), "end_date": end.isoformat()})
        return field, ranges
    try:
        weekdays = sorted({int(item.strip()) for item in value.split(",") if item.strip()})
    except ValueError as exc:
        raise ValueError("Usa dias ISO separados por coma, igual o todos.") from exc
    if not weekdays or any(day < 1 or day > 7 for day in weekdays):
        raise ValueError("Los dias deben estar entre 1=lunes y 7=domingo.")
    return field, weekdays


def _validate_rules_payload(rules: dict[str, Any]) -> None:
    minimum = rules.get("minimum_reservation_date")
    maximum = rules.get("maximum_reservation_date")
    if minimum and maximum and date.fromisoformat(maximum) < date.fromisoformat(minimum):
        raise ValueError("la fecha maxima no puede ser anterior a la minima")


def _rules_payload(order: dict[str, Any]) -> dict[str, Any]:
    weekdays = order.get("allowed_weekdays")
    return {
        "minimum_reservation_date": order.get("minimum_reservation_date"),
        "maximum_reservation_date": order.get("maximum_reservation_date"),
        "allowed_weekdays": list(weekdays) if isinstance(weekdays, list) else None,
        "excluded_date_ranges": list(order.get("excluded_date_ranges") or []),
    }
