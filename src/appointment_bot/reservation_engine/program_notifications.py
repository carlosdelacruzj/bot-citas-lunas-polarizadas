from __future__ import annotations

import logging

from appointment_bot.config import Settings
from appointment_bot.db.orders import record_order_program_listing
from appointment_bot.services.notifier import send_telegram_message

logger = logging.getLogger(__name__)


def notify_multiple_programs(
    settings: Settings,
    order_id: str | None,
    client_name: str | None,
    details: dict,
) -> None:
    should_notify = True
    if order_id is not None:
        try:
            should_notify = record_order_program_listing(order_id, details, settings=settings)
        except Exception:
            logger.exception("Could not persist program listing for %s", order_id)

    if not should_notify:
        logger.info("Program listing unchanged for %s; skipping alert", order_id)
        return

    rows = details.get("rows") if isinstance(details.get("rows"), list) else []
    pending_count = int(details.get("pending_count") or 0)
    if pending_count == 1:
        title = "UN SOLO TRAMITE PENDIENTE"
    elif pending_count > 1:
        title = "MULTIPLES TRAMITES PENDIENTES DETECTADOS"
    else:
        title = "LISTADO SIN TRAMITES PENDIENTES"
    lines = [
        title,
        f"Orden: {order_id or 'observer'}",
    ]
    if client_name:
        lines.append(f"Cliente: {client_name}")
    lines.append(f"Tramites: {details.get('program_count')}")
    lines.append(f"Pendientes: {details.get('pending_count')}")
    decision = str(details.get("decision") or "").strip()
    if decision == "single_pending_selected":
        lines.append("Accion: se eligio el unico PENDIENTE")
    elif decision == "multiple_pending_first_selected":
        lines.append("Accion: se eligio solo el primer PENDIENTE")
    elif decision == "target_selected":
        lines.append("Accion: se eligio el tramite objetivo")
    elif decision == "target_not_found":
        lines.append("Accion: detenido; no se encontro el tramite objetivo")
    elif decision == "target_not_pending":
        lines.append("Accion: detenido; el tramite objetivo no esta PENDIENTE")
    elif decision == "no_pending_blocked":
        lines.append("Accion: detenido sin PENDIENTE")
    for index, row in enumerate(rows[:5], start=1):
        if not isinstance(row, dict):
            continue
        vehicle = " ".join(
            str(row.get(key) or "").strip()
            for key in ("placa", "marca", "modelo", "color")
            if str(row.get(key) or "").strip()
        )
        status = str(row.get("status") or "sin estado").strip()
        expediente = str(row.get("expediente") or "").strip()
        lines.append(
            f"{index}. {status}"
            + (f" exp {expediente}" if expediente else "")
            + (f" - {vehicle}" if vehicle else "")
        )
    try:
        send_telegram_message(settings, "\n".join(lines))
    except Exception:
        logger.exception("Could not notify program listing")
