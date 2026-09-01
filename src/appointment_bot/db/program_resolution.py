from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.core.models import ServiceOrderCreateResult
from appointment_bot.core.service_packages import (
    SERVICE_PACKAGE_INTEGRAL,
    normalize_service_package,
    package_amounts,
    validate_service_package_compatibility,
)
from appointment_bot.core.statuses import sanitize_details
from appointment_bot.db.common import (
    _connection,
    _credential_cipher,
    _database_url,
    _now,
    _settings,
    init_database,
)
from appointment_bot.db.order_contacts import _optional_clean_text
from appointment_bot.db.remote_control_audit import (
    record_remote_control_audit_in_connection,
)
from appointment_bot.db.service_order_repository import persist_service_order

COMMUNICATION_DECISIONS = {
    "client_already_informed",
    "keep_without_send",
    "preview_single_confirmation",
}

PROGRAM_LISTING_ROW_FIELDS = (
    "action_index",
    "expediente",
    "motivo",
    "tipo",
    "placa",
    "marca",
    "modelo",
    "motor",
    "color",
    "status",
    "cells",
)


class ProgramResolutionConflict(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProgramResolutionNotFound(ValueError):
    code = "program_order_not_found"


def record_order_program_listing(
    order_id: str,
    details: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    listing = sanitize_details(details) or {}
    signature = json.dumps(
        _canonical_program_listing_snapshot(listing),
        sort_keys=True,
        ensure_ascii=True,
        default=str,
    )
    with _connection(_database_url(settings)) as connection:
        previous = connection.execute(
            "SELECT program_listing FROM order_state WHERE order_id = %s FOR UPDATE",
            (order_id,),
        ).fetchone()
        previous_payload = previous["program_listing"] if previous is not None else None
        previous_signature = (
            previous_payload.get("signature") if isinstance(previous_payload, dict) else None
        )
        changed = previous_signature != signature
        previous_revision = (
            int(previous_payload.get("revision") or 0)
            if isinstance(previous_payload, dict)
            else 0
        )
        payload = {
            "signature": signature,
            "revision": previous_revision + 1 if changed else max(previous_revision, 1),
            "details": listing,
            "updated_at": _now(),
        }
        if not changed and isinstance(previous_payload, dict):
            resolution = previous_payload.get("resolution")
            if isinstance(resolution, dict):
                payload["resolution"] = resolution
        connection.execute(
            """
            INSERT INTO order_state (order_id, program_listing)
            VALUES (%s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                program_listing = excluded.program_listing
            """,
            (order_id, Jsonb(payload)),
        )
    return changed


def _canonical_program_listing_snapshot(details: dict[str, Any]) -> dict[str, Any]:
    rows = details.get("rows")
    if not isinstance(rows, list):
        return {"rows": []}
    return {
        "rows": [
            {field: row.get(field) for field in PROGRAM_LISTING_ROW_FIELDS}
            for row in rows
            if isinstance(row, dict)
        ]
    }


def get_order_program_listing(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            "SELECT program_listing FROM order_state WHERE order_id = %s",
            (order_id,),
        ).fetchone()
    value = row["program_listing"] if row is not None else None
    return value if isinstance(value, dict) else None


def resolve_service_order_programs(
    order_id: str,
    *,
    resolution: str,
    listing_signature: str,
    communication_decision: str,
    actor: str,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    children: list[dict[str, Any]] | None = None,
    confirm_same_commercial_terms: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    resolution = resolution.strip().lower()
    if resolution not in {"one", "all", "pause"}:
        raise ValueError("resolution must be one, all or pause.")
    if communication_decision not in COMMUNICATION_DECISIONS:
        raise ValueError(
            "communication_decision must be client_already_informed, "
            "keep_without_send or preview_single_confirmation."
        )
    if resolution == "pause" and communication_decision == "preview_single_confirmation":
        raise ValueError("pause cannot prepare a customer confirmation preview.")
    if not listing_signature:
        raise ValueError("listing_signature is required.")
    actor = " ".join(actor.split())[:80]
    if not actor:
        raise ValueError("An authenticated actor is required.")

    now = _now()
    with _connection(_database_url(settings)) as connection:
        locked = connection.execute(
            """
            SELECT so.*, pa.username, pa.document_type, pa.password,
                   COALESCE(NULLIF(a.full_name, ''), a.document_number) AS applicant_name,
                   os.program_listing, os.preflight_status, os.preflight_details,
                   (
                       so.lease_owner IS NOT NULL
                       AND so.lease_expires_at > CURRENT_TIMESTAMP
                   ) AS has_active_lease
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            JOIN order_state os ON os.order_id = so.order_id
            WHERE so.order_id = %s
            FOR UPDATE OF so, os
            """,
            (order_id,),
        ).fetchone()
        if locked is None:
            raise ProgramResolutionNotFound(f"No existe la orden: {order_id}")
        listing = locked["program_listing"]
        if not isinstance(listing, dict) or not isinstance(listing.get("details"), dict):
            raise ProgramResolutionConflict(
                "program_listing_missing",
                "La orden no conserva un listado de tramites resoluble.",
            )
        if listing.get("signature") != listing_signature:
            raise ProgramResolutionConflict(
                "program_listing_stale",
                "El listado de tramites cambio; refresca y confirma nuevamente.",
            )
        pending_rows = _pending_program_rows(listing["details"])
        if len(pending_rows) < 2 and resolution in {"all", "pause"}:
            raise ProgramResolutionConflict(
                "program_resolution_not_required",
                "La cuenta ya no tiene multiples tramites pendientes.",
            )

        previous_resolution = listing.get("resolution")
        requested_fingerprint = {
            "resolution": resolution,
            "communication_decision": communication_decision,
            "program_expediente": _optional_clean_text(program_expediente),
            "program_plate": _optional_clean_text(program_plate),
            "children": sorted(
                children or [],
                key=lambda item: str(item.get("program_expediente") or "")
                if isinstance(item, dict)
                else "",
            ),
            "confirm_same_commercial_terms": bool(confirm_same_commercial_terms),
        }
        if isinstance(previous_resolution, dict) and previous_resolution.get(
            "request"
        ) == requested_fingerprint:
            return {
                "status": "already_applied",
                "order_id": order_id,
                "listing_signature": listing_signature,
                "listing_revision": int(listing.get("revision") or 1),
                **previous_resolution.get("result", {}),
            }
        if isinstance(previous_resolution, dict):
            raise ProgramResolutionConflict(
                "program_resolution_already_applied",
                "Esta revision del listado ya tiene una resolucion aplicada.",
            )

        if str(locked["status"]) != "paused":
            raise ProgramResolutionConflict(
                "program_resolution_invalid_state",
                "La orden debe estar pausada antes de resolver sus tramites.",
            )
        preflight_details = locked["preflight_details"]
        if (
            str(locked["preflight_status"]) != "failed"
            or not isinstance(preflight_details, dict)
            or preflight_details.get("error_type")
            != "multiple_pending_resolution_required"
        ):
            raise ProgramResolutionConflict(
                "program_resolution_preflight_conflict",
                "La orden no conserva el bloqueo de preflight por multiples tramites.",
            )
        if bool(locked["has_active_lease"]):
            raise ProgramResolutionConflict(
                "program_resolution_active_lease",
                "La orden tiene un lease activo y no puede resolverse en paralelo.",
            )
        active_attempt = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM reservation_attempts
                WHERE order_id = %s
                  AND status IN ('intent', 'pending', 'unknown')
            ) AS active
            """,
            (order_id,),
        ).fetchone()
        if bool(active_attempt and active_attempt["active"]):
            raise ProgramResolutionConflict(
                "program_resolution_active_attempt",
                "La orden tiene un intento de reserva activo o ambiguo.",
            )

        preview_rows: list[dict[str, Any]] = []
        result: dict[str, Any]
        if resolution == "pause":
            connection.execute(
                "UPDATE service_orders SET status = 'paused', updated_at = %s "
                "WHERE order_id = %s",
                (now, order_id),
            )
            result = {
                "resolution": "pause",
                "parent_order_id": order_id,
                "parent_archived": False,
                "preflight_scheduled": False,
            }
        elif resolution == "one":
            selected = _select_pending_program(
                pending_rows,
                program_expediente=program_expediente,
                program_plate=program_plate,
            )
            connection.execute(
                """
                UPDATE service_orders
                SET program_expediente = %s, program_plate = %s,
                    status = 'paused', updated_at = %s
                WHERE order_id = %s
                """,
                (
                    _optional_clean_text(selected.get("expediente")),
                    _optional_clean_text(selected.get("placa")),
                    now,
                    order_id,
                ),
            )
            result = {
                "resolution": "one",
                "parent_order_id": order_id,
                "parent_archived": False,
                "selected_program": selected,
                "preflight_scheduled": True,
            }
            preview_rows = [selected]
        else:
            _ensure_program_split_has_no_financial_history(connection, locked)
            specs = _commercial_specs_for_pending_rows(
                locked,
                pending_rows,
                children=children,
                confirm_same=confirm_same_commercial_terms,
            )
            created = _create_program_children_in_connection(
                connection,
                parent=locked,
                pending_rows=pending_rows,
                commercial_specs=specs,
                listing=listing,
                settings=settings,
            )
            connection.execute(
                "UPDATE service_orders SET status = 'archived', updated_at = %s "
                "WHERE order_id = %s",
                (now, order_id),
            )
            result = {
                "resolution": "all",
                "parent_order_id": order_id,
                "parent_archived": True,
                "service_orders": [
                    {
                        "order_id": item.order_id,
                        "applicant_id": item.applicant_id,
                        "portal_account_id": item.portal_account_id,
                    }
                    for item in created
                ],
                "preflight_scheduled": False,
            }
            preview_rows = pending_rows
        if communication_decision == "preview_single_confirmation":
            result["communication_preview"] = _program_resolution_preview(
                locked["applicant_name"], preview_rows
            )
        result["communication_decision"] = communication_decision
        audit_id = record_remote_control_audit_in_connection(
            connection,
            actor=actor,
            action="resolve_service_order_programs",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            detail=(
                f"resolution={resolution}; listing_revision={listing.get('revision')}; "
                f"communication_decision={communication_decision}"
            ),
        )
        result["audit_id"] = audit_id
        resolution_payload = {
            "request": requested_fingerprint,
            "actor": actor,
            "decided_at": now,
            "result": result,
        }
        listing["resolution"] = resolution_payload
        listing["updated_at"] = now
        connection.execute(
            "UPDATE order_state SET program_listing = %s WHERE order_id = %s",
            (Jsonb(listing), order_id),
        )
    return {
        "status": "applied",
        "order_id": order_id,
        "listing_signature": listing_signature,
        "listing_revision": int(listing.get("revision") or 1),
        **result,
    }


def _pending_program_rows(details: dict[str, Any]) -> list[dict[str, Any]]:
    rows = details.get("rows")
    if not isinstance(rows, list):
        return []
    return [
        dict(row)
        for row in rows
        if isinstance(row, dict)
        and str(row.get("status") or "").strip().casefold() == "pendiente"
    ]


def _normalized_program_value(value: object, *, remove_punctuation: bool = False) -> str:
    normalized = "".join(str(value or "").split()).casefold()
    if remove_punctuation:
        return "".join(character for character in normalized if character.isalnum())
    return normalized


def _select_pending_program(
    pending_rows: list[dict[str, Any]],
    *,
    program_expediente: str | None,
    program_plate: str | None,
) -> dict[str, Any]:
    expediente_key = _normalized_program_value(program_expediente)
    plate_key = _normalized_program_value(program_plate, remove_punctuation=True)
    if not expediente_key and not plate_key:
        raise ValueError("one requires program_expediente or program_plate.")
    matches = [
        row
        for row in pending_rows
        if (
            not expediente_key
            or _normalized_program_value(row.get("expediente")) == expediente_key
        )
        and (
            not plate_key
            or _normalized_program_value(row.get("placa"), remove_punctuation=True)
            == plate_key
        )
    ]
    if len(matches) != 1:
        raise ProgramResolutionConflict(
            "program_target_not_unique",
            "El expediente o la placa no identifica un unico tramite PENDIENTE.",
        )
    return matches[0]


def _ensure_program_split_has_no_financial_history(
    connection: Connection,
    parent: dict[str, Any],
) -> None:
    financial = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM payments WHERE order_id = %s
        ) OR EXISTS (
            SELECT 1 FROM payment_receipts WHERE order_id = %s
        ) OR EXISTS (
            SELECT 1 FROM finance_entries WHERE order_id = %s
        ) AS has_financial_history
        """,
        (parent["order_id"], parent["order_id"], parent["order_id"]),
    ).fetchone()
    if str(parent["service_package"]) == SERVICE_PACKAGE_INTEGRAL or bool(
        financial and financial["has_financial_history"]
    ):
        raise ProgramResolutionConflict(
            "program_resolution_financial_allocation_required",
            "La orden tiene paquete integral o historia financiera; define primero "
            "como se asignan cobros y costos entre los tramites.",
        )


def _commercial_specs_for_pending_rows(
    parent: dict[str, Any],
    pending_rows: list[dict[str, Any]],
    *,
    children: list[dict[str, Any]] | None,
    confirm_same: bool,
) -> dict[str, dict[str, Any]]:
    expedientes = [_optional_clean_text(row.get("expediente")) for row in pending_rows]
    if any(not expediente for expediente in expedientes) or len(set(expedientes)) != len(
        expedientes
    ):
        raise ProgramResolutionConflict(
            "program_pending_expediente_not_unique",
            "Cada tramite PENDIENTE debe tener un expediente unico para resolver todos.",
        )
    if confirm_same:
        if children:
            raise ValueError(
                "Use children or confirm_same_commercial_terms, but not both."
            )
        shared = {
            "charge_required": bool(parent["charge_required"]),
            "service_type": str(parent["service_type"]),
            "service_package": str(parent["service_package"]),
            "reservation_price": parent["reservation_price"],
            "minimum_reservation_date": parent["minimum_date"],
            "maximum_reservation_date": parent["maximum_date"],
            "allowed_weekdays": parent["allowed_weekdays"],
            "excluded_date_ranges": parent["excluded_date_ranges"],
        }
        return {str(expediente): dict(shared) for expediente in expedientes}
    if not children:
        raise ValueError(
            "all requires complete children or confirm_same_commercial_terms=true."
        )
    required = {
        "program_expediente",
        "charge_required",
        "service_type",
        "service_package",
        "reservation_price",
        "minimum_reservation_date",
        "maximum_reservation_date",
        "allowed_weekdays",
        "excluded_date_ranges",
    }
    specs: dict[str, dict[str, Any]] = {}
    for index, spec in enumerate(children):
        if not isinstance(spec, dict):
            raise ValueError(f"children[{index}] must be an object.")
        missing = required - set(spec)
        if missing:
            raise ValueError(
                f"children[{index}] is missing: {', '.join(sorted(missing))}."
            )
        expediente = _optional_clean_text(spec.get("program_expediente"))
        if not expediente or expediente not in expedientes or expediente in specs:
            raise ValueError(
                f"children[{index}].program_expediente is invalid or duplicated."
            )
        service_type = str(spec["service_type"]).strip().lower()
        if service_type not in {"standard", "selected_weekday", "custom"}:
            raise ValueError(f"children[{index}].service_type is invalid.")
        price = Decimal(str(spec["reservation_price"])).quantize(Decimal("0.01"))
        package = normalize_service_package(str(spec["service_package"]))
        validate_service_package_compatibility(package, service_type)
        package_amounts(package, price)
        if not isinstance(spec["charge_required"], bool):
            raise ValueError(f"children[{index}].charge_required must be boolean.")
        if package == SERVICE_PACKAGE_INTEGRAL:
            raise ProgramResolutionConflict(
                "program_integral_split_unsupported",
                "Una division por tramites no puede crear ordenes hijas integrales.",
            )
        specs[expediente] = {
            **spec,
            "service_type": service_type,
            "service_package": package,
            "reservation_price": price,
        }
    if set(specs) != set(expedientes):
        raise ValueError("children must define every pending expediente exactly once.")
    return specs


def _create_program_children_in_connection(
    connection: Connection,
    *,
    parent: dict[str, Any],
    pending_rows: list[dict[str, Any]],
    commercial_specs: dict[str, dict[str, Any]],
    listing: dict[str, Any],
    settings: Settings,
) -> list[ServiceOrderCreateResult]:
    password = _credential_cipher(settings).decrypt(str(parent["password"]))
    created: list[ServiceOrderCreateResult] = []
    for row in pending_rows:
        expediente = str(_optional_clean_text(row.get("expediente")))
        spec = commercial_specs[expediente]
        result = persist_service_order(
            document_number=str(parent["username"]),
            password=password,
            document_type=str(parent["document_type"]),
            priority=int(parent["priority"]),
            applicant_name=str(parent["applicant_name"]),
            charge_required=bool(spec["charge_required"]),
            service_type=str(spec["service_type"]),
            service_package=str(spec["service_package"]),
            reservation_price=Decimal(str(spec["reservation_price"])),
            minimum_reservation_date=spec.get("minimum_reservation_date"),
            maximum_reservation_date=spec.get("maximum_reservation_date"),
            allowed_weekdays=spec.get("allowed_weekdays"),
            excluded_date_ranges=spec.get("excluded_date_ranges"),
            parent_order_id=str(parent["order_id"]),
            program_expediente=expediente,
            program_plate=_optional_clean_text(row.get("placa")),
            require_preflight=False,
            settings=settings,
            _connection_override=connection,
        )
        connection.execute(
            """
            UPDATE order_state
            SET preflight_status = 'validated',
                preflight_message = %s,
                preflight_validated_at = %s,
                preflight_details = %s,
                program_listing = %s
            WHERE order_id = %s
            """,
            (
                "Tramite objetivo confirmado por resolucion explicita del operador.",
                _now(),
                Jsonb(
                    {
                        "error_type": None,
                        "program_target": row,
                        "source": "program_resolution_all",
                    }
                ),
                Jsonb(listing),
                result.order_id,
            ),
        )
        created.append(result)
    return created


def _program_resolution_preview(
    applicant_name: object,
    pending_rows: list[dict[str, Any]],
) -> str:
    lines = [
        f"Hola, {str(applicant_name or 'cliente').strip()}.",
        "Confirmamos que atenderemos los siguientes tramites:",
    ]
    for row in pending_rows:
        expediente = str(row.get("expediente") or "sin expediente").strip()
        plate = str(row.get("placa") or "sin placa").strip()
        lines.append(f"- Expediente {expediente} | Placa {plate}")
    lines.append("Este texto es solo una previsualizacion y aun no fue enviado.")
    return "\n".join(lines)


def split_service_order_programs(
    order_id: str,
    *,
    archive_parent: bool = True,
    settings: Settings | None = None,
) -> list[ServiceOrderCreateResult]:
    raise ProgramResolutionConflict(
        "explicit_program_resolution_required",
        "La division directa fue retirada. Usa program-resolution con listado, "
        "condiciones comerciales y decision de comunicacion explicitas.",
    )
