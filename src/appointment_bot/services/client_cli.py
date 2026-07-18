from __future__ import annotations

import argparse
import getpass
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.core.contacts import CONTACT_SOURCES, ContactValidationError
from appointment_bot.db.common import init_database
from appointment_bot.db.orders import (
    add_or_update_service_order_contact,
    create_service_order,
    has_active_child_service_orders,
    list_service_order_summaries,
    mark_order_done,
    mark_order_preflight_failed,
    mark_payment_paid,
    mark_service_order_no_charge,
    set_order_paused,
    split_service_order_programs,
    update_service_order_document_type,
)
from appointment_bot.db.runs import list_run_details_between
from appointment_bot.reports.evidence import export_evidence_summary
from appointment_bot.reports.observation import export_optimization_observation
from appointment_bot.reports.status import (
    generate_daily_report_image,
    generate_status_report_images,
)
from appointment_bot.reports.weekly import LIMA_TZ, export_weekly_report
from appointment_bot.services.notifier import send_telegram_message
from appointment_bot.services.order_preflight import validate_order_preflight

SENSITIVE_FIELDS = {"password", "login_password"}
PREFERRED_ORDER_FIELDS = (
    "order_id",
    "applicant_name",
    "document_number_masked",
    "contact_name",
    "contact_source",
    "contact_whatsapp_masked",
    "priority",
    "charge_required",
    "status",
    "reservation_status",
    "payment_status",
    "amount_agreed",
    "amount_paid",
    "parent_order_id",
    "program_expediente",
    "program_plate",
    "minimum_reservation_hour",
    "minimum_reservation_date",
    "maximum_reservation_date",
    "allowed_weekdays",
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
        "--document-type",
        choices=("dni", "foreign_resident_card"),
        default="dni",
        help="Tipo de documento usado para ingresar al portal.",
    )
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
    order_add_parser.add_argument(
        "--contact-name",
        required=True,
        help="Nombre de quien contacta.",
    )
    order_add_parser.add_argument(
        "--contact-source",
        required=True,
        choices=CONTACT_SOURCES,
        help="Origen del contacto, por ejemplo whatsapp o tiktok.",
    )
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
    order_add_parser.add_argument(
        "--maximum-reservation-date",
        help="Fecha maxima permitida para reservar, en formato YYYY-MM-DD o DD/MM/YYYY.",
    )
    order_add_parser.add_argument(
        "--allowed-weekdays",
        help=("Dias permitidos ISO separados por coma: 1=lunes ... 6=sabado, 7=domingo."),
    )
    order_add_parser.add_argument("--program-expediente", help="Expediente objetivo.")
    order_add_parser.add_argument("--program-plate", help="Placa objetivo.")
    order_add_parser.add_argument("--parent-order-id", help="Orden padre si es suborden.")

    split_parser = subparsers.add_parser(
        "order-split-programs",
        help="Crea subordenes por cada tramite pendiente detectado.",
    )
    split_parser.add_argument("order_id", help="Orden con listado de tramites guardado.")
    split_parser.add_argument(
        "--keep-parent-active",
        action="store_true",
        help="No archiva la orden generica despues de crear subordenes.",
    )

    document_type_parser = subparsers.add_parser(
        "order-document-type",
        help="Actualiza el tipo de documento usado para ingresar al portal.",
    )
    document_type_parser.add_argument("order_id")
    document_type_parser.add_argument(
        "document_type",
        choices=("dni", "foreign_resident_card"),
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
    evidence_summary_parser = subparsers.add_parser(
        "evidence-summary",
        help="Genera CSV/Markdown compactos para revisar optimizaciones.",
    )
    evidence_summary_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Cantidad de dias hacia atras a incluir.",
    )
    weekly_parser = subparsers.add_parser(
        "weekly-report",
        help="Genera un reporte operacional comparable por rango exacto.",
    )
    weekly_parser.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD.")
    weekly_parser.add_argument("--end", required=True, help="Fecha final inclusiva YYYY-MM-DD.")
    weekly_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/operations"),
        help="Directorio para la salida fechada.",
    )
    observation_parser = subparsers.add_parser(
        "optimization-observation",
        help="Genera linea base observacional sin cambiar el flujo de reserva.",
    )
    observation_parser.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD.")
    observation_parser.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD.")
    observation_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/optimization"),
        help="Directorio para la salida fechada.",
    )
    observation_parser.add_argument(
        "--set-baseline",
        action="store_true",
        help="Promueve explicitamente este rango como linea base vigente.",
    )
    weekly_parser.add_argument(
        "--notify",
        action="store_true",
        help="Envia por Telegram las alertas detectadas.",
    )
    evidence_summary_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/evidence"),
        help="Directorio donde se guardan los resumenes de evidencia.",
    )

    contact_parser = subparsers.add_parser("contact", help="Agrega o actualiza contacto.")
    contact_parser.add_argument("order_id", help="ID del trabajo de reserva.")
    contact_parser.add_argument("--whatsapp", help="WhatsApp de contacto.")
    contact_parser.add_argument("--contact-name", help="Nombre de quien contacta.")
    contact_parser.add_argument(
        "--contact-source",
        choices=CONTACT_SOURCES,
        help="Origen del contacto, por ejemplo whatsapp o tiktok.",
    )

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
        try:
            result = create_service_order(
                document_number=args.document,
                document_type=args.document_type,
                password=password,
                priority=args.priority,
                contact_whatsapp=args.whatsapp,
                contact_name=args.contact_name,
                contact_source=args.contact_source,
                applicant_name=args.applicant_name,
                charge_required=not args.no_charge,
                minimum_reservation_hour=args.minimum_reservation_hour,
                minimum_reservation_date=args.minimum_reservation_date,
                maximum_reservation_date=args.maximum_reservation_date,
                allowed_weekdays=_parse_allowed_weekdays(args.allowed_weekdays),
                parent_order_id=args.parent_order_id,
                program_expediente=args.program_expediente,
                program_plate=args.program_plate,
            )
        except ContactValidationError as exc:
            parser.error(str(exc))
        print(f"Trabajo guardado: {result.order_id}")
        try:
            validation = validate_order_preflight(result.order_id)
        except Exception as exc:
            mark_order_preflight_failed(result.order_id, str(exc))
            print(f"Validacion fallida: {exc}")
            print("El trabajo quedo pausado y no entrara a la cola.")
            return 1
        if validation["status"] == "validated":
            print("Validacion del portal completada. El trabajo ya esta activo.")
            return 0
        print(f"Validacion fallida: {validation.get('message') or 'error desconocido'}")
        print("El trabajo quedo pausado y no entrara a la cola.")
        return 1

    if args.command == "order-split-programs":
        results = split_service_order_programs(
            args.order_id,
            archive_parent=not args.keep_parent_active,
        )
        for result in results:
            print(f"Suborden guardada: {result.order_id}")
        return 0

    if args.command == "order-document-type":
        try:
            update_service_order_document_type(args.order_id, args.document_type)
        except ValueError as exc:
            parser.error(str(exc))
        print(f"Tipo de documento actualizado: {args.order_id} -> {args.document_type}")
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

    if args.command == "evidence-summary":
        now = datetime.now(UTC)
        result = export_evidence_summary(
            list_run_details_between(
                started_at=now - timedelta(days=max(args.days, 1)),
                finished_at=now + timedelta(seconds=1),
            ),
            output_dir=args.output_dir,
            days=args.days,
            now=now,
            update_current=True,
        )
        print(f"Eventos exportados: {result.event_count}")
        print(f"CSV generado: {result.csv_path}")
        print(f"Resumen generado: {result.markdown_path}")
        return 0

    if args.command == "weekly-report":
        try:
            start = date.fromisoformat(args.start)
            end = date.fromisoformat(args.end)
        except ValueError:
            parser.error("--start y --end deben usar YYYY-MM-DD.")
        days = (end - start).days + 1
        query_start = datetime.combine(start - timedelta(days=days), time.min, LIMA_TZ)
        query_end = datetime.combine(end + timedelta(days=1), time.min, LIMA_TZ)
        result = export_weekly_report(
            list_run_details_between(
                started_at=query_start.astimezone(UTC),
                finished_at=query_end.astimezone(UTC),
            ),
            start=start,
            end=end,
            output_dir=args.output_dir,
        )
        print(f"Runs medidos: {result.run_count}")
        print(f"Reporte generado: {result.markdown_path}")
        print(f"Metricas generadas: {result.metrics_path}")
        print(f"Resumen vigente: {result.latest_path}")
        if args.notify and result.alerts:
            settings = load_settings(require_login=False)
            send_telegram_message(
                settings,
                "ALERTA OPERACIONAL\n" + "\n".join(f"- {alert}" for alert in result.alerts),
            )
        return 0

    if args.command == "optimization-observation":
        try:
            start = date.fromisoformat(args.start)
            end = date.fromisoformat(args.end)
        except ValueError:
            parser.error("--start y --end deben usar YYYY-MM-DD.")
        if end < start:
            parser.error("--end no puede ser anterior a --start.")
        query_start = datetime.combine(start, time.min, LIMA_TZ)
        query_end = datetime.combine(end + timedelta(days=1), time.min, LIMA_TZ)
        result = export_optimization_observation(
            list_run_details_between(
                started_at=query_start.astimezone(UTC),
                finished_at=query_end.astimezone(UTC),
            ),
            start=start,
            end=end,
            output_dir=args.output_dir,
            promote_baseline=args.set_baseline,
        )
        print(f"Runs observados: {result.run_count}")
        print(f"Reporte generado: {result.report_path}")
        if result.baseline_path is not None:
            print(f"Linea base vigente: {result.baseline_path}")
        else:
            print("Linea base vigente sin cambios; usa --set-baseline para reemplazarla.")
        return 0

    if args.command == "contact":
        if not args.whatsapp and not args.contact_name:
            parser.error("Debes indicar --whatsapp o --contact-name.")
        try:
            add_or_update_service_order_contact(
                args.order_id,
                contact_whatsapp=args.whatsapp,
                contact_name=args.contact_name,
                contact_source=args.contact_source,
            )
        except ContactValidationError as exc:
            parser.error(str(exc))
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
        if has_active_child_service_orders(args.order_id):
            parser.error("No se puede activar una orden padre con subordenes activas.")
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


def _parse_allowed_weekdays(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
