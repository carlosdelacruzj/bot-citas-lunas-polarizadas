from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

SENSITIVE_FIELDS = {"password", "login_password"}
PREFERRED_LIST_FIELDS = ("id", "client_id", "name", "username", "priority", "active", "done")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="appointment-bot-client",
        description="Administra clientes del appointment bot.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Agrega o actualiza un cliente.")
    add_parser.add_argument("--id", dest="client_id", required=True, help="ID interno del cliente.")
    add_parser.add_argument("--name", required=True, help="Nombre visible del cliente.")
    add_parser.add_argument("--username", required=True, help="Usuario de acceso del cliente.")
    add_parser.add_argument("--password", required=True, help="Clave de acceso del cliente.")
    add_parser.add_argument(
        "--priority",
        required=True,
        type=int,
        help="Prioridad numerica del cliente.",
    )

    subparsers.add_parser("list", help="Lista clientes registrados.")

    activate_parser = subparsers.add_parser("activate", help="Activa un cliente.")
    activate_parser.add_argument("client_id", help="ID interno del cliente.")

    pause_parser = subparsers.add_parser("pause", help="Pausa un cliente.")
    pause_parser.add_argument("client_id", help="ID interno del cliente.")

    done_parser = subparsers.add_parser("done", help="Marca un cliente como completado.")
    done_parser.add_argument("client_id", help="ID interno del cliente.")

    return parser


def _row_to_dict(row: Any) -> dict[str, Any]:
    if is_dataclass(row) and not isinstance(row, type):
        return asdict(row)

    if isinstance(row, Mapping):
        return dict(row)

    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}

    if isinstance(row, Sequence) and not isinstance(row, str):
        fields = ("id", "name", "username", "priority", "active", "done")
        return {field: value for field, value in zip(fields, row, strict=False)}

    return {"client": str(row)}


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return ""
    return str(value)


def _load_database_api():
    from appointment_bot.services.database import (
        add_client,
        init_database,
        list_clients,
        mark_client_done,
        set_client_active,
    )

    return add_client, init_database, list_clients, mark_client_done, set_client_active


def _print_clients(clients: Sequence[Any]) -> None:
    rows = [
        {key: value for key, value in _row_to_dict(client).items() if key not in SENSITIVE_FIELDS}
        for client in clients
    ]
    if not rows:
        print("No hay clientes registrados.")
        return

    columns = [field for field in PREFERRED_LIST_FIELDS if any(field in row for row in rows)]
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

    (
        add_client,
        init_database,
        list_clients,
        mark_client_done,
        set_client_active,
    ) = _load_database_api()
    init_database()

    if args.command == "add":
        add_client(args.client_id, args.name, args.username, args.password, args.priority)
        print(f"Cliente guardado: {args.client_id}")
        return 0

    if args.command == "list":
        _print_clients(list_clients())
        return 0

    if args.command == "activate":
        set_client_active(args.client_id, True)
        print(f"Cliente activado: {args.client_id}")
        return 0

    if args.command == "pause":
        set_client_active(args.client_id, False)
        print(f"Cliente pausado: {args.client_id}")
        return 0

    if args.command == "done":
        mark_client_done(args.client_id)
        print(f"Cliente completado: {args.client_id}")
        return 0

    parser.error(f"Comando no soportado: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
