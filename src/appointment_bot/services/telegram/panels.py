from __future__ import annotations

import logging
from collections import deque
from decimal import Decimal
from typing import Any

from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.constants import CLIENTS_PAGE_SIZE
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.presentation import (
    _applicant_display_name,
    _display_text,
    _format_lima_datetime,
    _format_operator_date,
    _is_failed_run,
    _main_menu_markup,
    _money_text,
    _order_status_counts,
    _order_status_label,
    _safe_run_message,
    format_order_detail,
    format_order_rules,
)
from appointment_bot.services.telegram.validation import (
    _money_value,
    _payment_balance,
    _valid_order_id,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _send_main_menu(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    counts: dict[str, int] = {}
    try:
        inbox = admin_api.get_operator_inbox()
        summary = inbox.get("summary")
        if isinstance(summary, dict):
            counts["pending"] = int(summary.get("total") or 0)
        orders = admin_api.get_service_orders()
        counts["queue"] = sum(str(order.get("status") or "") == "ready" for order in orders)
        counts["payments"] = sum(
            str(order.get("reservation_status") or "") == "confirmed"
            and str(order.get("payment_status") or "") == "pending"
            for order in orders
        )
    except (TelegramControlError, TypeError, ValueError):
        counts = {}
    telegram.send_message(
        chat_id,
        "OPERACION DIARIA\n\nElige que deseas revisar o hacer.",
        reply_markup=_main_menu_markup(counts),
    )


def _send_tools_menu(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    rows = [
        [{"text": "Historial de clientes", "callback_data": "ui:clients:1"}],
        [{"text": "Oportunidades", "callback_data": "ui:opportunity:show"}],
        [{"text": "Errores recientes", "callback_data": "ui:errors:show"}],
    ]
    try:
        captcha_enabled = bool(admin_api.get_health().get("captcha_shadow_enabled"))
    except TelegramControlError:
        captcha_enabled = False
    if captcha_enabled:
        rows.insert(
            1,
            [{"text": "Etiquetar CAPTCHA", "callback_data": "ui:captcha:start"}],
        )
    rows.append([{"text": "Volver", "callback_data": "ui:menu:main"}])
    telegram.send_message(
        chat_id,
        "HERRAMIENTAS\n\nFunciones de revision y control menos frecuentes.",
        reply_markup={"inline_keyboard": rows},
    )


def _send_clients(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        page = int(arguments) if arguments else 1
        if page < 1:
            raise ValueError
    except ValueError:
        telegram.send_message(chat_id, "Uso: /clientes [pagina]")
        return
    try:
        orders = admin_api.get_service_orders()
    except TelegramControlError as exc:
        logger.warning("Could not list service orders: %s", exc)
        telegram.send_message(chat_id, "No pude consultar la cola en este momento.")
        return
    total_pages = max(1, (len(orders) + CLIENTS_PAGE_SIZE - 1) // CLIENTS_PAGE_SIZE)
    if page > total_pages:
        telegram.send_message(chat_id, f"La ultima pagina disponible es {total_pages}.")
        return
    counts = _order_status_counts(orders)
    start = (page - 1) * CLIENTS_PAGE_SIZE
    visible = orders[start : start + CLIENTS_PAGE_SIZE]
    lines = [
        f"CLIENTES - PAGINA {page}/{total_pages}",
        "",
        (
            f"Activos: {counts['active']} | Pausados: {counts['paused']} | "
            f"Pendientes de pago: {counts['payment_pending']} | Cerrados: {counts['closed']}"
        ),
        "",
    ]
    for order in visible:
        applicant_name = _applicant_display_name(order)
        contact_name = _display_text(order.get("contact_name") or "Sin contacto", 32)
        lines.append(
            f"{order.get('order_id', 'sin-id')}\n"
            f"Titular: {applicant_name}\n"
            f"Contacto: {contact_name}\n"
            f"Estado: {_order_status_label(order.get('status'))} | "
            f"Prioridad: {order.get('priority', 0)}"
        )
    if not visible:
        lines.append("No hay clientes registrados.")
    if page < total_pages:
        lines.extend(["", f"Siguiente: /clientes {page + 1}"])
    keyboard: list[list[dict[str, str]]] = []
    for order in visible:
        order_id = str(order.get("order_id") or "")
        if not order_id or len(f"om:{order_id}:show_clients".encode()) > 64:
            continue
        label = _applicant_display_name(order)
        if label == "Titular no identificado por el portal":
            label = str(order.get("contact_name") or order_id)
        keyboard.append(
            [{"text": _display_text(label, 34), "callback_data": f"om:{order_id}:show_clients"}]
        )
    navigation: list[dict[str, str]] = []
    if page > 1:
        navigation.append({"text": "Anterior", "callback_data": f"ui:clients:{page - 1}"})
    if page < total_pages:
        navigation.append({"text": "Siguiente", "callback_data": f"ui:clients:{page + 1}"})
    if navigation:
        keyboard.append(navigation)
    keyboard.append(
        [
            {"text": "Actualizar", "callback_data": f"ui:clients:{page}"},
            {"text": "Menu", "callback_data": "ui:menu:main"},
        ]
    )
    telegram.send_message(
        chat_id,
        "\n\n".join(lines),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_queue(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    page = _parse_list_page(arguments, "/cola [pagina]", chat_id, telegram)
    if page is None:
        return
    try:
        orders = [
            order
            for order in admin_api.get_service_orders()
            if str(order.get("status") or "") == "ready"
        ]
    except TelegramControlError as exc:
        logger.warning("Could not list queued service orders: %s", exc)
        telegram.send_message(chat_id, "No pude consultar la cola en este momento.")
        return
    _send_operational_order_list(
        chat_id,
        page,
        orders,
        title="BUSCANDO CUPO",
        empty_text="No hay usuarios buscando cupo en este momento.",
        callback_subject="queue",
        telegram=telegram,
    )


def _send_pending_attention(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    page = _parse_list_page(arguments, "/pendientes [pagina]", chat_id, telegram)
    if page is None:
        return
    try:
        payload = admin_api.get_operator_inbox()
    except TelegramControlError as exc:
        logger.warning("Could not read operator inbox: %s", exc)
        telegram.send_message(
            chat_id,
            "La bandeja de pendientes aun no esta disponible en el Admin API. "
            "Actualiza el servicio e intenta nuevamente.",
            reply_markup={
                "inline_keyboard": [[{"text": "Menu", "callback_data": "ui:menu:main"}]]
            },
        )
        return
    raw_items = payload.get("items")
    summary = payload.get("summary")
    items = (
        [item for item in raw_items if isinstance(item, dict)]
        if isinstance(raw_items, list)
        else []
    )
    summary = summary if isinstance(summary, dict) else {}
    total_pages = max(1, (len(items) + CLIENTS_PAGE_SIZE - 1) // CLIENTS_PAGE_SIZE)
    if page > total_pages:
        telegram.send_message(chat_id, f"La ultima pagina disponible es {total_pages}.")
        return
    start = (page - 1) * CLIENTS_PAGE_SIZE
    visible = items[start : start + CLIENTS_PAGE_SIZE]
    summary_labels = (
        ("access", "Acceso"),
        ("paused", "Pausados"),
        ("contact", "Contacto"),
        ("whatsapp", "WhatsApp"),
        ("payment", "Cobros"),
        ("postpayment", "Postpago"),
        ("messages", "Mensajes"),
    )
    counts = [
        f"{label}: {int(summary.get(key) or 0)}"
        for key, label in summary_labels
        if int(summary.get(key) or 0) > 0
    ]
    lines = [
        f"PENDIENTES - PAGINA {page}/{total_pages}",
        "",
        f"Total: {int(summary.get('total') or len(items))}",
    ]
    if counts:
        lines.append(" | ".join(counts))
    keyboard: list[list[dict[str, str]]] = []
    for item in visible:
        order_id = str(item.get("order_id") or "")
        title = _display_text(item.get("title") or "Pendiente operativo", 80)
        description = _display_text(item.get("description") or "Requiere revision.", 180)
        applicant_name = _display_text(item.get("applicant_name") or order_id, 60)
        action = str(item.get("action") or "view_order")
        action_label = _display_text(item.get("action_label") or "Ver orden", 34)
        lines.extend(["", f"{title}\n{applicant_name}\n{description}"])
        if not order_id:
            continue
        if action in {"mark_payment", "register_payment"}:
            callback_data = f"py:{order_id}:choose_pending"
        elif action == "correct_credentials":
            callback_data = f"om:{order_id}:access"
        elif action == "revalidate":
            callback_data = f"om:{order_id}:validate"
        elif action in {"resolve_programs", "resolve_multiple_pending", "program_resolution"}:
            callback_data = f"pr:{order_id}:show"
        else:
            callback_data = f"om:{order_id}:show_pending"
            if action not in {"view_order"}:
                lines.append(
                    "Accion: revisar en el dashboard; Telegram no enviara ni reintentara."
                )
                action_label = "Ver orden"
        if len(callback_data.encode()) <= 64:
            button_label = _display_text(f"{action_label} - {applicant_name}", 56)
            keyboard.append([{"text": button_label, "callback_data": callback_data}])
    if not items:
        lines.extend(["", "No hay usuarios que requieran seguimiento."])
    navigation: list[dict[str, str]] = []
    if page > 1:
        navigation.append({"text": "Anterior", "callback_data": f"ui:pending:{page - 1}"})
    if page < total_pages:
        navigation.append({"text": "Siguiente", "callback_data": f"ui:pending:{page + 1}"})
    if navigation:
        keyboard.append(navigation)
    keyboard.append(
        [
            {"text": "Actualizar", "callback_data": f"ui:pending:{page}"},
            {"text": "Menu", "callback_data": "ui:menu:main"},
        ]
    )
    telegram.send_message(
        chat_id,
        "\n\n".join(lines),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_pending_payments(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    page = _parse_list_page(arguments, "/cobros [pagina]", chat_id, telegram)
    if page is None:
        return
    try:
        orders = [
            order
            for order in admin_api.get_service_orders()
            if str(order.get("status") or "") == "reserved_payment_pending"
            and str(order.get("payment_status") or "") == "pending"
        ]
    except TelegramControlError as exc:
        logger.warning("Could not list pending payments: %s", exc)
        telegram.send_message(chat_id, "No pude consultar los cobros en este momento.")
        return
    total_balance = sum((_payment_balance(order) for order in orders), Decimal("0"))
    _send_operational_order_list(
        chat_id,
        page,
        orders,
        title=f"PAGOS PENDIENTES - {len(orders)} | SALDO S/{_money_text(total_balance)}",
        empty_text="No hay reservas con pago pendiente.",
        callback_subject="payments",
        telegram=telegram,
        payment_mode=True,
    )


def _parse_list_page(
    arguments: str,
    usage: str,
    chat_id: str,
    telegram: TelegramBotApi,
) -> int | None:
    try:
        page = int(arguments) if arguments else 1
        if page < 1:
            raise ValueError
    except ValueError:
        telegram.send_message(chat_id, f"Uso: {usage}")
        return None
    return page


def _send_operational_order_list(
    chat_id: str,
    page: int,
    orders: list[dict[str, Any]],
    *,
    title: str,
    empty_text: str,
    callback_subject: str,
    telegram: TelegramBotApi,
    payment_mode: bool = False,
) -> None:
    total_pages = max(1, (len(orders) + CLIENTS_PAGE_SIZE - 1) // CLIENTS_PAGE_SIZE)
    if page > total_pages:
        telegram.send_message(chat_id, f"La ultima pagina disponible es {total_pages}.")
        return
    start = (page - 1) * CLIENTS_PAGE_SIZE
    visible = orders[start : start + CLIENTS_PAGE_SIZE]
    lines = [f"{title} - PAGINA {page}/{total_pages}", ""]
    keyboard: list[list[dict[str, str]]] = []
    for order in visible:
        order_id = str(order.get("order_id") or "")
        applicant_name = _applicant_display_name(order)
        if payment_mode:
            agreed = _money_value(order.get("amount_agreed")) or Decimal("0")
            paid = _money_value(order.get("amount_paid")) or Decimal("0")
            contact = (
                order.get("contact_whatsapp_masked")
                or order.get("contact_whatsapp_username_masked")
                or "sin contacto operativo"
            )
            appointment = " ".join(
                part
                for part in (
                    str(order.get("reservation_date") or "").strip(),
                    str(order.get("reservation_hour") or "").strip(),
                )
                if part
            ) or "sin fecha"
            communication_state = str(order.get("whatsapp_message_action_state") or "")
            communication_note = (
                "\nAtencion: revisa primero la comunicacion inicial."
                if communication_state in {"manual_required", "failed", "uncertain"}
                else ""
            )
            lines.append(
                f"{applicant_name}\n"
                f"Orden: {order_id}\n"
                f"Cita: {appointment}\n"
                f"Contacto: {contact}\n"
                f"Acordado: S/{_money_text(agreed)} | Abonado: S/{_money_text(paid)} | "
                f"Saldo: S/{_money_text(max(agreed - paid, Decimal('0')))}"
                f"{communication_note}"
            )
            callback_data = f"py:{order_id}:choose_payments"
            button_label = f"Gestionar pago - {_display_text(applicant_name, 25)}"
        else:
            lines.append(
                f"{applicant_name}\n"
                f"Orden: {order_id}\n"
                f"Estado: {_order_status_label(order.get('status'))} | "
                f"Prioridad: {order.get('priority', 0)}"
            )
            callback_data = f"om:{order_id}:show_{callback_subject}"
            button_label = _display_text(applicant_name, 34)
        if order_id and len(callback_data.encode()) <= 64:
            keyboard.append([{"text": button_label, "callback_data": callback_data}])
    if not visible:
        lines.append(empty_text)
    navigation: list[dict[str, str]] = []
    if page > 1:
        navigation.append(
            {"text": "Anterior", "callback_data": f"ui:{callback_subject}:{page - 1}"}
        )
    if page < total_pages:
        navigation.append(
            {"text": "Siguiente", "callback_data": f"ui:{callback_subject}:{page + 1}"}
        )
    if navigation:
        keyboard.append(navigation)
    keyboard.append(
        [
            {"text": "Actualizar", "callback_data": f"ui:{callback_subject}:{page}"},
            {"text": "Menu", "callback_data": "ui:menu:main"},
        ]
    )
    telegram.send_message(
        chat_id,
        "\n\n".join(lines),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_order_query(
    chat_id: str,
    command: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    order_id = arguments.strip()
    if not _valid_order_id(order_id):
        telegram.send_message(chat_id, f"Uso: /{command} ORDER_ID")
        return
    try:
        if command == "cliente":
            order = admin_api.get_service_order(order_id)
        else:
            order = next(
                (
                    item
                    for item in admin_api.get_service_orders()
                    if item.get("order_id") == order_id
                ),
                None,
            )
    except TelegramControlError as exc:
        logger.warning("Could not read service order: %s", exc)
        telegram.send_message(chat_id, "No pude consultar esa orden.")
        return
    if order is None:
        telegram.send_message(chat_id, "No pude encontrar esa orden.")
        return
    response = format_order_rules(order) if command == "reglas" else format_order_detail(order)
    reply_markup = None
    if command == "reglas":
        reply_markup = {
            "inline_keyboard": [
                [{"text": "Editar reglas", "callback_data": f"om:{order_id}:editrules"}],
                [{"text": "Volver al cliente", "callback_data": f"om:{order_id}:show"}],
            ]
        }
    telegram.send_message(chat_id, response, reply_markup=reply_markup)


def _send_priority_menu(
    chat_id: str,
    order_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        order = admin_api.get_service_order(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not prepare priority menu: %s", exc)
        telegram.send_message(chat_id, "No pude consultar la prioridad.")
        return
    current = int(order.get("priority") or 0)
    presets = [
        ("Normal", 0),
        ("Enfocada", 100),
        ("Exclusiva", 200),
    ]
    telegram.send_message(
        chat_id,
        f"PRIORIDAD\n\nOrden: {order_id}\nValor actual: {current}\n\n"
        "Normal mantiene la cola general; Enfocada prioriza la orden; "
        "Exclusiva concentra la busqueda en ella.\n\nElige un valor:",
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": label, "callback_data": f"pq:{order_id}:{value}"}
                    for label, value in presets
                ],
                [{"text": "Volver", "callback_data": f"om:{order_id}:show"}],
            ]
        },
    )


def _send_order_panel(
    chat_id: str,
    order_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    recent_orders: dict[str, deque[str]],
    *,
    return_subject: str = "clients",
) -> None:
    try:
        order = admin_api.get_service_order(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not open service order panel: %s", exc)
        telegram.send_message(chat_id, "No pude abrir ese cliente.")
        return
    history = recent_orders[chat_id]
    if order_id in history:
        history.remove(order_id)
    history.appendleft(order_id)
    keyboard = [
        [
            {"text": "Reglas", "callback_data": f"om:{order_id}:rules"},
            {"text": "Prioridad", "callback_data": f"om:{order_id}:priority"},
        ],
    ]
    if str(order.get("preflight_status") or "") == "failed":
        preflight_details = order.get("preflight_details")
        error_type = (
            str(preflight_details.get("error_type") or "")
            if isinstance(preflight_details, dict)
            else ""
        )
        if error_type == "multiple_pending_resolution_required":
            keyboard.append([{
                "text": "Resolver programas",
                "callback_data": f"pr:{order_id}:show",
            }])
        elif error_type == "invalid_credentials":
            keyboard.append([{
                "text": "Corregir acceso",
                "callback_data": f"om:{order_id}:access",
            }])
        else:
            keyboard.append([{
                "text": "Reintentar validacion",
                "callback_data": f"om:{order_id}:validate",
            }])
    if (
        str(order.get("status") or "") == "reserved_payment_pending"
        and str(order.get("payment_status") or "") == "pending"
    ):
        keyboard.append([{
            "text": "Gestionar pago",
            "callback_data": f"py:{order_id}:choose_{return_subject}",
        }])
    return_options = {
        "pending": ("Pendientes", "ui:pending:1"),
        "queue": ("Buscando cupo", "ui:queue:1"),
        "payments": ("Por cobrar", "ui:payments:1"),
        "summary": ("Citas proximas", "ui:summary:show"),
        "clients": ("Historial", "ui:clients:1"),
    }
    return_label, return_callback = return_options.get(
        return_subject,
        ("Menu", "ui:menu:main"),
    )
    keyboard.extend(
        [
            [{"text": "Actualizar", "callback_data": f"om:{order_id}:show"}],
            [
                {"text": return_label, "callback_data": return_callback},
                {"text": "Menu", "callback_data": "ui:menu:main"},
            ],
        ]
    )
    telegram.send_message(
        chat_id,
        format_order_detail(order),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_search_results(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    query = " ".join(arguments.lower().split())
    if len(query) < 2:
        telegram.send_message(
            chat_id,
            "Escribe /buscar seguido de nombre, contacto, documento visible u ORDER_ID.\n"
            "Ejemplo: /buscar Pedro",
            reply_markup={"inline_keyboard": [[{"text": "Menu", "callback_data": "ui:menu:main"}]]},
        )
        return
    try:
        matches = admin_api.search_service_orders(query)
    except TelegramControlError as exc:
        logger.warning("Could not search service orders: %s", exc)
        telegram.send_message(chat_id, "No pude buscar clientes en este momento.")
        return
    keyboard = [
        [{
            "text": _display_text(
                _applicant_display_name(order)
                if _applicant_display_name(order) != "Titular no identificado por el portal"
                else order.get("contact_name") or order.get("order_id"),
                36,
            ),
            "callback_data": f"om:{order.get('order_id')}:show_menu",
        }]
        for order in matches
        if len(f"om:{order.get('order_id')}:show_menu".encode()) <= 64
    ]
    keyboard.append([{"text": "Menu", "callback_data": "ui:menu:main"}])
    telegram.send_message(
        chat_id,
        f"BUSQUEDA: {arguments.strip()}\n\n"
        + (f"Coincidencias: {len(matches)}" if matches else "No encontre coincidencias."),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_daily_summary(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        reminders = admin_api.get_appointment_reminders()
    except TelegramControlError as exc:
        logger.warning("Could not prepare upcoming appointments: %s", exc)
        telegram.send_message(chat_id, "No pude consultar las citas proximas.")
        return
    raw_candidates = reminders.get("candidates")
    candidates = (
        [item for item in raw_candidates if isinstance(item, dict)]
        if isinstance(raw_candidates, list)
        else []
    )
    appointment_day = _format_operator_date(reminders.get("appointment_day"))
    lines = [
        "CITAS PROXIMAS / RESUMEN",
        "",
        f"Fecha: {appointment_day}",
        f"Citas: {len(candidates)}",
    ]
    keyboard: list[list[dict[str, str]]] = []
    for candidate in candidates[:8]:
        order_id = str(candidate.get("order_id") or "")
        applicant_name = _display_text(
            candidate.get("applicant_name") or order_id or "Titular no identificado",
            60,
        )
        date_label = _display_text(
            candidate.get("appointment_date_label") or appointment_day,
            40,
        )
        hour = _display_text(candidate.get("appointment_hour") or "sin hora", 24)
        site = _display_text(candidate.get("site") or "sede no registrada", 60)
        lines.extend(["", f"{applicant_name}\n{date_label} {hour}\n{site}"])
        callback_data = f"om:{order_id}:show_summary"
        if order_id and len(callback_data.encode()) <= 64:
            keyboard.append(
                [{"text": _display_text(applicant_name, 36), "callback_data": callback_data}]
            )
    if not candidates:
        lines.extend(["", "No hay citas elegibles para la fecha objetivo."])
    keyboard.append(
        [
            {"text": "Actualizar", "callback_data": "ui:summary:show"},
            {"text": "Menu", "callback_data": "ui:menu:main"},
        ]
    )
    telegram.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup={"inline_keyboard": keyboard},
    )


def _send_recent_errors(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        worker = admin_api.get_worker()
        runs = admin_api.get_runs(limit=50)
    except TelegramControlError as exc:
        logger.warning("Could not read recent errors: %s", exc)
        telegram.send_message(chat_id, "No pude consultar los incidentes recientes.")
        return
    failures = [run for run in runs if _is_failed_run(run)][:5]
    lines = ["ULTIMOS ERRORES", ""]
    if worker.get("last_error"):
        lines.append("El worker conserva un error reciente. Revisa el dashboard para el detalle.")
    if not failures and not worker.get("last_error"):
        lines.append("No hay errores recientes en las ultimas 50 ejecuciones.")
    for run in failures:
        timestamp = _format_lima_datetime(run.get("finished_at") or run.get("started_at"))
        order_id = run.get("order_id") or "sin orden"
        status = run.get("status") or "error"
        message = _safe_run_message(run.get("message"))
        lines.append(
            f"{timestamp or 'Sin fecha'} | {order_id}\n"
            f"{status}: {message}"
        )
    telegram.send_message(
        chat_id,
        "\n\n".join(lines),
        reply_markup={
            "inline_keyboard": [[
                {"text": "Actualizar", "callback_data": "ui:errors:show"},
                {"text": "Menu", "callback_data": "ui:menu:main"},
            ]]
        },
    )


def _send_payment_menu(
    chat_id: str,
    order_id: str,
    return_subject: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        order = admin_api.get_service_order(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not prepare payment menu: %s", exc)
        telegram.send_message(chat_id, "No pude consultar ese cobro.")
        return
    if (
        str(order.get("status") or "") != "reserved_payment_pending"
        or str(order.get("payment_status") or "") != "pending"
    ):
        telegram.send_message(chat_id, "Ese cobro ya no esta pendiente. Actualiza la lista.")
        return
    agreed = _money_value(order.get("amount_agreed"))
    paid = _money_value(order.get("amount_paid")) or Decimal("0")
    if agreed is None or agreed <= 0:
        telegram.send_message(chat_id, "La orden no tiene un monto acordado valido.")
        return
    telegram.send_message(
        chat_id,
        "GESTIONAR PAGO\n\n"
        f"Cliente: {_applicant_display_name(order)}\n"
        f"Acordado: S/{_money_text(agreed)}\n"
        f"Abonado: S/{_money_text(paid)}\n"
        f"Saldo: S/{_money_text(max(agreed - paid, Decimal('0')))}\n\n"
        "El pago completo encola el postpago. Un abono conserva el cobro pendiente.",
        reply_markup={
            "inline_keyboard": [
                [{
                    "text": f"Confirmar pago completo · S/{_money_text(agreed)}",
                    "callback_data": f"py:{order_id}:full_{return_subject}",
                }],
                [{
                    "text": "Registrar abono",
                    "callback_data": f"py:{order_id}:partial_{return_subject}",
                }],
                [{"text": "Cancelar", "callback_data": "ui:cancel:guided"}],
            ]
        },
    )
