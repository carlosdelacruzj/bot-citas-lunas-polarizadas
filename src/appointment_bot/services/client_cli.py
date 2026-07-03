from __future__ import annotations

import argparse
import getpass
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from appointment_bot.services.postgres_database import (
    add_or_update_service_order_contact,
    create_service_order,
    init_database,
    list_service_order_summaries,
    mark_order_done,
    mark_payment_paid,
    mark_service_order_no_charge,
    set_order_paused,
)
from appointment_bot.services.status_reports import (
    generate_daily_report_image,
    generate_status_report_images,
)

SENSITIVE_FIELDS = {"password", "login_password"}
PREFERRED_ORDER_FIELDS = (
    "order_id",
    "applicant_name",
    "document_number_masked",
    "contact_name",
    "contact_whatsapp_masked",
    "priority",
    "charge_required",
    "status",
    "reservation_status",
    "payment_status",
    "amount_agreed",
    "amount_paid",
    "minimum_reservation_hour",
    "minimum_reservation_date",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="appointment-bot-client",
        description="Administra ordenes del appointment bot.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    order_add_parser = subparsers.add_parser("order-add", help="Crea un trabajo de reserva.")
    order_add_parser.add_argument("--document", required=True, help="DNI/documento del titular.")
    order_add_parser.add_argument(
        "--password",
        help="Clave de acceso. Si se omite, se solicita de forma oculta.",
    )
    order_add_parser.add_argument(
        "--priority",
        type=int,
        default=0,
        help="Prioridad numerica del trabajo.",
    )
    order_add_parser.add_argument("--whatsapp", help="WhatsApp de contacto.")
    order_add_parser.add_argument("--contact-name", help="Nombre de quien contacta.")
    order_add_parser.add_argument("--applicant-name", help="Nombre del titular si se conoce.")
    order_add_parser.add_argument(
        "--no-charge",
        action="store_true",
        help="Crea el trabajo sin cobro.",
    )
    order_add_parser.add_argument(
        "--minimum-reservation-hour",
        type=int,
        help="Hora minima permitida para reservar, por ejemplo 11.",
    )
    order_add_parser.add_argument(
        "--minimum-reservation-date",
        help="Fecha minima permitida para reservar, en formato YYYY-MM-DD o DD/MM/YYYY.",
    )

    subparsers.add_parser("orders", help="Lista trabajos de reserva.")

    status_report_parser = subparsers.add_parser(
        "status-report",
        help="Genera fichas PNG con la actividad de las ultimas 24 horas.",
    )
    status_report_parser.add_argument(
        "order_id",
        nargs="?",
        help="ID de una orden. Si se omite, genera todas las ordenes activas.",
    )
    status_report_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/status"),
        help="Directorio donde se guardan las fichas PNG.",
    )
    daily_report_parser = subparsers.add_parser(
        "daily-report",
        help="Genera el reporte general del dia.",
    )
    daily_report_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/daily"),
        help="Directorio donde se guarda el reporte general.",
    )

    contact_parser = subparsers.add_parser("contact", help="Agrega o actualiza WhatsApp.")
    contact_parser.add_argument("order_id", help="ID del trabajo de reserva.")
    contact_parser.add_argument("--whatsapp", required=True, help="WhatsApp de contacto.")
    contact_parser.add_argument("--contact-name", help="Nombre de quien contacta.")

    paid_parser = subparsers.add_parser("paid", help="Marca un trabajo como cobrado.")
    paid_parser.add_argument("order_id", help="ID del trabajo de reserva.")
    paid_parser.add_argument("--amount-paid", required=True, help="Monto cobrado.")
    paid_parser.add_argument("--amount-agreed", help="Monto pactado, si difiere.")

    no_charge_parser = subparsers.add_parser(
        "no-charge",
        help="Marca un trabajo como sin cobro.",
    )
    no_charge_parser.add_argument("order_id", help="ID del trabajo de reserva.")

    activate_parser = subparsers.add_parser("activate", help="Activa un trabajo.")
    activate_parser.add_argument("order_id", help="ID del trabajo de reserva.")

    pause_parser = subparsers.add_parser("pause", help="Pausa un trabajo.")
    pause_parser.add_argument("order_id", help="ID del trabajo de reserva.")

    done_parser = subparsers.add_parser("done", help="Marca un trabajo como completado.")
    done_parser.add_argument("order_id", help="ID del trabajo de reserva.")

    return parser


def _row_to_dict(row: Any) -> dict[str, Any]:
    if is_dataclass(row) and not isinstance(row, type):
        return asdict(row)

    if isinstance(row, Mapping):
        return dict(row)

    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}

    if isinstance(row, Sequence) and not isinstance(row, str):
        fields = ("id", "name", "username", "priority", "status")
        return {field: value for field, value in zip(fields, row, strict=False)}

    return {"row": str(row)}


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return ""
    return str(value)


def _print_rows(items: Sequence[Any], *, preferred_fields: Sequence[str]) -> None:
    rows = [
        {key: value for key, value in _row_to_dict(item).items() if key not in SENSITIVE_FIELDS}
        for item in items
    ]
    if not rows:
        print("No hay ordenes registradas.")
        return

    columns = [field for field in preferred_fields if any(field in row for row in rows)]
    extra_columns = sorted({key for row in rows for key in row if key not in columns})
    columns.extend(extra_columns)

    widths = {
        column: max(len(column), *(len(_format_value(row.get(column))) for row in rows))
        for column in columns
    }
    print("  ".join(column.ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print("  ".join(_format_value(row.get(column)).ljust(widths[column]) for column in columns))


def run(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    init_database()

    if args.command == "order-add":
        password = args.password or getpass.getpass("Clave del titular: ")
        if not password:
            parser.error("La clave del titular no puede estar vacia.")
        result = create_service_order(
            document_number=args.document,
            password=password,
            priority=args.priority,
            contact_whatsapp=args.whatsapp,
            contact_name=args.contact_name,
            applicant_name=args.applicant_name,
            charge_required=not args.no_charge,
            minimum_reservation_hour=args.minimum_reservation_hour,
            minimum_reservation_date=args.minimum_reservation_date,
        )
        print(f"Trabajo guardado: {result.order_id}")
        return 0

    if args.command == "orders":
        _print_rows(list_service_order_summaries(), preferred_fields=PREFERRED_ORDER_FIELDS)
        return 0

    if args.command == "status-report":
        orders = list_service_order_summaries()
        if args.order_id:
            orders = [order for order in orders if order.order_id == args.order_id]
            if not orders:
                parser.error(f"No existe la orden: {args.order_id}")
        else:
            orders = [order for order in orders if order.status == "ready"]
        if not orders:
            print("No hay ordenes activas para generar fichas.")
            return 0
        paths = generate_status_report_images(orders, output_dir=args.output_dir)
        for path in paths:
            print(f"Ficha generada: {path}")
        return 0

    if args.command == "daily-report":
        path = generate_daily_report_image(output_dir=args.output_dir)
        print(f"Reporte general generado: {path}")
        return 0

    if args.command == "contact":
        add_or_update_service_order_contact(
            args.order_id,
            contact_whatsapp=args.whatsapp,
            contact_name=args.contact_name,
        )
        print(f"Contacto actualizado: {args.order_id}")
        return 0

    if args.command == "paid":
        mark_payment_paid(
            args.order_id,
            amount_paid=args.amount_paid,
            amount_agreed=args.amount_agreed,
        )
        print(f"Cobro registrado: {args.order_id}")
        return 0

    if args.command == "no-charge":
        mark_service_order_no_charge(args.order_id)
        print(f"Trabajo sin cobro: {args.order_id}")
        return 0

    if args.command == "activate":
        set_order_paused(args.order_id, False)
        print(f"Trabajo activado: {args.order_id}")
        return 0

    if args.command == "pause":
        set_order_paused(args.order_id, True)
        print(f"Trabajo pausado: {args.order_id}")
        return 0

    if args.command == "done":
        mark_order_done(args.order_id, status="completed")
        print(f"Trabajo completado: {args.order_id}")
        return 0

    parser.error(f"Comando no soportado: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
