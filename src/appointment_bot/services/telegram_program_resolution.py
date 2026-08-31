from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from threading import Lock
from typing import Any, Protocol

logger = logging.getLogger(__name__)

ERROR_TYPE = "multiple_pending_resolution_required"
COMMUNICATION_DECISIONS = {
    "client_already_informed",
    "keep_without_send",
}


class ProgramResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ProgramResolutionDraft:
    payload: dict[str, Any]
    description: str
    requires_communication_decision: bool


class TelegramPort(Protocol):
    def send_message(
        self, chat_id: str, text: str, *, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


class AdminApiPort(Protocol):
    def get_service_order(self, order_id: str) -> dict[str, Any]: ...

    def resolve_service_order_programs(
        self, order_id: str, resolution: dict[str, Any], *, actor: str
    ) -> dict[str, Any]: ...


def resolution_details(order: dict[str, Any]) -> dict[str, Any] | None:
    details = order.get("preflight_details")
    if not isinstance(details, dict):
        return None
    error_type = str(
        order.get("preflight_error_type") or details.get("error_type") or ""
    )
    return details if error_type == ERROR_TYPE else None


def pending_programs(details: dict[str, Any]) -> list[dict[str, Any]]:
    programs = (
        details.get("pending_programs")
        or details.get("programs")
        or details.get("rows")
    )
    if not isinstance(programs, list):
        return []
    return [
        program
        for program in programs
        if isinstance(program, dict)
        and str(program.get("status") or "").strip().casefold() == "pendiente"
    ]


def requires_dashboard(order: dict[str, Any], details: dict[str, Any]) -> bool:
    commercial_mode = str(
        details.get("commercial_mode") or order.get("commercial_mode") or ""
    ).strip().casefold()
    return (
        str(order.get("service_type") or "").strip().casefold() == "custom"
        or str(order.get("service_package") or "").strip().casefold()
        in {"custom", "integral"}
        or commercial_mode in {"custom", "shared", "shared_total", "shared_price"}
    )


def build_panel(order_id: str, order: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    details = resolution_details(order)
    if details is None:
        raise ProgramResolutionError(
            "Esta orden ya no requiere resolver programas multiples. Actualiza el cliente."
        )
    programs = pending_programs(details)
    listing_token = _listing_token(details)
    lines = [
        "RESOLVER PROGRAMAS PENDIENTES",
        "",
        f"Orden: {order_id}",
        "La orden seguira pausada hasta confirmar una decision.",
        "",
    ]
    keyboard: list[list[dict[str, str]]] = []
    for index, program in enumerate(programs):
        expediente = _expediente(program)
        if not expediente:
            continue
        plate = _plate(program)
        lines.append(
            f"PENDIENTE | Expediente {expediente}"
            + (f" | Placa {plate}" if plate else "")
        )
        callback_data = f"pr:{order_id}:one{index}-{listing_token}"
        if len(callback_data.encode()) <= 64:
            keyboard.append([{
                "text": f"Resolver {expediente}"[:56],
                "callback_data": callback_data,
            }])
    if not programs:
        lines.append("No quedan filas PENDIENTE en el listado actual.")
    elif requires_dashboard(order, details):
        lines.extend([
            "",
            "Esta orden usa precio compartido o configuracion custom. "
            "Resuelvela en el Dashboard; Telegram no replicara condiciones.",
        ])
        keyboard = []
    else:
        callback_data = f"pr:{order_id}:all-{listing_token}"
        if len(callback_data.encode()) <= 64:
            keyboard.append([{
                "text": "Resolver todos con mismas condiciones",
                "callback_data": callback_data,
            }])
    pause_callback = f"pr:{order_id}:pause-{listing_token}"
    if len(pause_callback.encode()) <= 64:
        keyboard.append([{"text": "Mantener pausado", "callback_data": pause_callback}])
    keyboard.append([
        {"text": "Actualizar", "callback_data": f"pr:{order_id}:show"},
        {"text": "Volver", "callback_data": f"om:{order_id}:show_pending"},
    ])
    return "\n".join(lines), {"inline_keyboard": keyboard}


def prepare_resolution(order: dict[str, Any], action: str) -> ProgramResolutionDraft:
    details = resolution_details(order)
    if details is None:
        raise ProgramResolutionError(
            "El listado ya cambio o la orden ya no requiere esta resolucion. Actualiza."
        )
    signature = str(details.get("listing_signature") or "").strip()
    if not signature:
        raise ProgramResolutionError(
            "El listado no tiene una firma verificable. La orden permanece pausada; "
            "resuelvela en el Dashboard."
        )
    action, separator, expected_token = action.rpartition("-")
    if not separator or expected_token != _listing_token(details):
        raise ProgramResolutionError(
            "El listado cambio desde que abriste estos botones. Actualiza antes de elegir."
        )
    programs = pending_programs(details)
    if requires_dashboard(order, details) and action != "pause":
        raise ProgramResolutionError(
            "Esta orden usa precio compartido o configuracion custom. "
            "Resuelvela en el Dashboard; Telegram no replicara condiciones."
        )
    payload: dict[str, Any] = {"listing_signature": signature}
    if action.startswith("one") and action.removeprefix("one").isdigit():
        index = int(action.removeprefix("one"))
        if index >= len(programs):
            raise ProgramResolutionError("Ese expediente ya no esta pendiente. Actualiza.")
        expediente = _expediente(programs[index])
        if not expediente:
            raise ProgramResolutionError(
                "La fila pendiente no tiene expediente exacto. Resuelvela en el Dashboard."
            )
        payload.update({"resolution": "one", "program_expediente": expediente})
        plate = _plate(programs[index])
        if plate:
            payload["program_plate"] = plate
        return ProgramResolutionDraft(
            payload, f"resolver solo el expediente {expediente}", True
        )
    if action == "all":
        if not programs:
            raise ProgramResolutionError("Ya no quedan programas pendientes. Actualiza.")
        payload.update({
            "resolution": "all",
            "confirm_same_commercial_terms": True,
        })
        return ProgramResolutionDraft(
            payload, "resolver todos con las mismas condiciones por expediente", True
        )
    if action == "pause":
        payload["resolution"] = "pause"
        return ProgramResolutionDraft(payload, "mantener la orden pausada", True)
    raise ProgramResolutionError("La decision seleccionada no es valida.")


def with_communication_decision(
    payload: dict[str, Any], decision: str
) -> dict[str, Any]:
    if decision not in COMMUNICATION_DECISIONS:
        raise ProgramResolutionError("La decision de comunicacion no es valida.")
    updated = dict(payload)
    updated["communication_decision"] = decision
    return updated


def communication_preview(result: dict[str, Any]) -> str:
    return str(result.get("communication_preview") or "").strip()


def send_panel(
    chat_id: str,
    order_id: str,
    telegram: TelegramPort,
    admin_api: AdminApiPort,
) -> None:
    try:
        text, markup = build_panel(order_id, admin_api.get_service_order(order_id))
    except RuntimeError as exc:
        logger.warning("Could not open program resolution panel: %s", exc)
        telegram.send_message(chat_id, "No pude actualizar los programas de esa orden.")
        return
    except ProgramResolutionError as exc:
        telegram.send_message(chat_id, str(exc))
        return
    telegram.send_message(chat_id, text, reply_markup=markup)


def request_resolution(
    chat_id: str,
    order_id: str,
    action: str,
    telegram: TelegramPort,
    admin_api: AdminApiPort,
    pending_changes: dict[str, Any],
    lock: Lock,
    change_factory: Callable[..., Any],
    *,
    confirmation_ttl_seconds: int,
) -> None:
    try:
        draft = prepare_resolution(admin_api.get_service_order(order_id), action)
    except RuntimeError as exc:
        logger.warning("Could not prepare program resolution: %s", exc)
        telegram.send_message(chat_id, "No pude actualizar el listado de programas.")
        return
    except ProgramResolutionError as exc:
        telegram.send_message(chat_id, str(exc))
        return
    operation_id = secrets.token_hex(6)
    change = change_factory(
        operation_id=operation_id,
        chat_id=chat_id,
        action="program_resolution",
        order_id=order_id,
        original={"description": draft.description},
        updated=draft.payload,
        expires_at=time.monotonic() + confirmation_ttl_seconds,
        return_subject="pending",
    )
    with lock:
        stale_ids = [
            pending_id
            for pending_id, pending_change in pending_changes.items()
            if pending_change.chat_id == chat_id
        ]
        for pending_id in stale_ids:
            pending_changes.pop(pending_id, None)
        pending_changes[operation_id] = change
    if not draft.requires_communication_decision:
        send_confirmation(change, telegram)
        return
    telegram.send_message(
        chat_id,
        "DECISION DE COMUNICACION\n\n"
        f"Accion: {draft.description}.\n"
        "Telegram no enviara WhatsApp en ningun caso.",
        reply_markup={"inline_keyboard": [
            [{"text": "Cliente ya informado", "callback_data": f"pr:{operation_id}:informed"}],
            [{"text": "Mantener sin enviar", "callback_data": f"pr:{operation_id}:keep"}],
            [{"text": "Cancelar", "callback_data": f"oc:{operation_id}:no"}],
        ]},
    )


def set_communication_decision(
    chat_id: str,
    operation_id: str,
    action: str,
    telegram: TelegramPort,
    pending_changes: dict[str, Any],
    lock: Lock,
) -> None:
    decision = {
        "informed": "client_already_informed",
        "keep": "keep_without_send",
    }.get(action, "")
    with lock:
        change = pending_changes.get(operation_id)
        if (
            change is None
            or change.chat_id != chat_id
            or change.action != "program_resolution"
            or change.expires_at <= time.monotonic()
        ):
            change = None
        else:
            try:
                change = replace(
                    change,
                    updated=with_communication_decision(change.updated, decision),
                )
            except ProgramResolutionError:
                change = None
            else:
                pending_changes[operation_id] = change
    if change is None:
        telegram.send_message(chat_id, "La decision ya vencio. Actualiza el cliente.")
        return
    send_confirmation(change, telegram)


def send_confirmation(change: Any, telegram: TelegramPort) -> None:
    decision_label = {
        "client_already_informed": "cliente ya informado",
        "keep_without_send": "mantener sin enviar",
    }.get(str(change.updated.get("communication_decision") or ""), "no definida")
    telegram.send_message(
        change.chat_id,
        "CONFIRMAR RESOLUCION\n\n"
        f"Orden: {change.order_id}\n"
        f"Accion: {change.original['description']}\n"
        f"Comunicacion: {decision_label}.\n\n"
        "No se enviara WhatsApp. La confirmacion vence en 2 minutos.",
        reply_markup={"inline_keyboard": [[
            {"text": "Confirmar", "callback_data": f"oc:{change.operation_id}:yes"},
            {"text": "Cancelar", "callback_data": f"oc:{change.operation_id}:no"},
        ]]},
    )


def execute_resolution(
    change: Any,
    telegram: TelegramPort,
    admin_api: AdminApiPort,
    *,
    actor: str,
    audit: Callable[..., None],
    display_text: Callable[[Any, int], str],
) -> None:
    if str(change.updated.get("communication_decision") or "") not in COMMUNICATION_DECISIONS:
        telegram.send_message(
            change.chat_id,
            "No aplique la resolucion: falta una decision de comunicacion valida.",
        )
        return
    try:
        result = admin_api.resolve_service_order_programs(
            change.order_id, change.updated, actor=actor
        )
    except RuntimeError as exc:
        logger.warning("Program resolution %s failed: %s", change.operation_id, exc)
        stale = "HTTP 409" in str(exc)
        telegram.send_message(
            change.chat_id,
            (
                "El listado cambio mientras confirmabas. No aplique nada. "
                "Actualiza y elige nuevamente."
                if stale
                else "No pude aplicar la resolucion. La orden permanece pausada; "
                "actualiza antes de volver a intentar."
            ),
            reply_markup={"inline_keyboard": [[
                {"text": "Actualizar", "callback_data": f"pr:{change.order_id}:show"}
            ]]},
        )
        audit(
            actor=actor,
            action="program_resolution",
            status="stale" if stale else "failed",
            target_type="service_order",
            target_id=change.order_id,
            operation_id=change.operation_id,
            detail=str(exc),
        )
        return
    preview = communication_preview(result)
    text = (
        "Resolucion aplicada.\n"
        f"Solicitud: {change.operation_id[:8]}\n"
        f"Orden: {change.order_id}\n"
        "WhatsApp: no enviado desde Telegram."
    )
    if preview:
        text += f"\n\nVISTA PREVIA - NO ENVIADA\n{display_text(preview, 1800)}"
    telegram.send_message(
        change.chat_id,
        text,
        reply_markup={"inline_keyboard": [[
            {"text": "Ver cliente", "callback_data": f"om:{change.order_id}:show"},
            {"text": "Pendientes", "callback_data": "ui:pending:1"},
        ]]},
    )
    audit(
        actor=actor,
        action="program_resolution",
        status="applied",
        target_type="service_order",
        target_id=change.order_id,
        operation_id=change.operation_id,
    )


def _expediente(program: dict[str, Any]) -> str:
    return str(
        program.get("expediente")
        or program.get("expediente_number")
        or program.get("file_number")
        or ""
    ).strip()


def _plate(program: dict[str, Any]) -> str:
    return str(
        program.get("placa")
        or program.get("plate")
        or program.get("license_plate")
        or ""
    ).strip()


def _listing_token(details: dict[str, Any]) -> str:
    signature = str(details.get("listing_signature") or "")
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]
