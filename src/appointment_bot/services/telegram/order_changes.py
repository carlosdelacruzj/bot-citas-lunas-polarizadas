from __future__ import annotations

import hashlib
import logging
import secrets
import time
from decimal import Decimal
from threading import Lock
from typing import Any

from appointment_bot.services import telegram_program_resolution
from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.audit import _record_audit_safe, _telegram_actor
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.constants import CONFIRMATION_TTL_SECONDS
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.models import PendingOrderChange, PendingWorkerConfirmation
from appointment_bot.services.telegram.order_queries import _wait_for_order_preflight
from appointment_bot.services.telegram.presentation import (
    _applicant_display_name,
    _display_text,
    _format_order_change_comparison,
    _money_text,
)
from appointment_bot.services.telegram.validation import (
    _money_value,
    _valid_order_id,
    _validated_payment_amount,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _request_priority_change(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> None:
    parts = arguments.split()
    if len(parts) != 2 or not _valid_order_id(parts[0]):
        telegram.send_message(chat_id, "Uso: /prioridad ORDER_ID VALOR")
        return
    try:
        priority = int(parts[1])
        if priority < 0:
            raise ValueError
    except ValueError:
        telegram.send_message(chat_id, "La prioridad debe ser un entero no negativo.")
        return
    try:
        order = admin_api.get_service_order(parts[0])
    except TelegramControlError as exc:
        logger.warning("Could not prepare priority change: %s", exc)
        telegram.send_message(chat_id, "No pude encontrar o consultar esa orden.")
        return
    original_priority = int(order.get("priority") or 0)
    if priority == original_priority:
        telegram.send_message(chat_id, f"La prioridad ya es {priority}. No hay cambios.")
        return
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action="priority",
        order_id=parts[0],
        original={"priority": original_priority},
        updated={"priority": priority},
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)


def _request_credentials_change(
    chat_id: str,
    order_id: str,
    password: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
    *,
    return_subject: str,
) -> None:
    try:
        order = admin_api.get_service_order(order_id)
        credentials = admin_api.get_service_order_credentials(order_id)
    except TelegramControlError as exc:
        logger.warning("Could not prepare Telegram credential correction: %s", exc)
        telegram.send_message(
            chat_id,
            "No pude preparar la correccion. La contrasena no fue modificada.",
        )
        return
    preflight_details = order.get("preflight_details")
    error_type = (
        str(preflight_details.get("error_type") or "")
        if isinstance(preflight_details, dict)
        else ""
    )
    if (
        str(order.get("preflight_status") or "") != "failed"
        or error_type != "invalid_credentials"
    ):
        telegram.send_message(
            chat_id,
            "El acceso ya no figura como credenciales rechazadas. "
            "No se guardo la contrasena.",
        )
        return
    document_number = str(credentials.get("username") or "").strip()
    document_type = str(credentials.get("document_type") or "").strip()
    current_password = str(credentials.get("password") or "")
    if not document_number or not document_type or not current_password:
        telegram.send_message(
            chat_id,
            "No pude verificar el acceso protegido actual. No se realizo ningun cambio.",
        )
        return
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action="credentials",
        order_id=order_id,
        original={
            "applicant_name": order.get("applicant_name") or "sin nombre",
            "document_number": document_number,
            "document_type": document_type,
            "password_sha256": hashlib.sha256(current_password.encode("utf-8")).hexdigest(),
            "preflight_cycle": int(order.get("preflight_cycle") or 0),
        },
        updated={
            "document_number": document_number,
            "document_type": document_type,
            "password": password,
        },
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
        return_subject=return_subject,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)


def _request_payment_change(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
    *,
    return_subject: str = "menu",
) -> None:
    parts = arguments.split()
    if len(parts) not in {1, 2} or not _valid_order_id(parts[0]):
        telegram.send_message(chat_id, "Uso: /pago ORDER_ID MONTO_TOTAL")
        return
    try:
        order = admin_api.get_service_order(parts[0])
    except TelegramControlError as exc:
        logger.warning("Could not prepare payment registration: %s", exc)
        telegram.send_message(chat_id, "No pude encontrar o consultar esa orden.")
        return
    if (
        str(order.get("status") or "") != "reserved_payment_pending"
        or str(order.get("payment_status") or "") != "pending"
    ):
        telegram.send_message(
            chat_id,
            "La orden ya no figura como reserva con pago pendiente. Actualiza Cobros.",
        )
        return
    agreed = _money_value(order.get("amount_agreed"))
    if agreed is None or agreed <= 0:
        telegram.send_message(chat_id, "La orden no tiene un monto acordado valido.")
        return
    try:
        paid = _validated_payment_amount(parts[1] if len(parts) == 2 else agreed)
    except ValueError as exc:
        telegram.send_message(chat_id, str(exc))
        return
    previous_paid = _money_value(order.get("amount_paid")) or Decimal("0")
    if paid <= previous_paid:
        telegram.send_message(
            chat_id,
            f"El total acumulado debe ser mayor que S/{_money_text(previous_paid)}.",
        )
        return
    action = "payment_partial" if paid < agreed else "payment_paid"
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action=action,
        order_id=parts[0],
        original={
            "applicant_name": _applicant_display_name(order),
            "amount_agreed": _money_text(agreed),
            "amount_paid": _money_text(previous_paid),
        },
        updated={
            "amount_agreed": _money_text(agreed),
            "amount_paid": _money_text(paid),
        },
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
        return_subject=return_subject,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)


def _store_order_change(
    change: PendingOrderChange,
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> None:
    with confirmation_lock:
        stale = [
            key
            for key, item in pending_order_changes.items()
            if item.chat_id == change.chat_id
        ]
        for key in stale:
            pending_order_changes.pop(key, None)
        pending_order_changes[change.operation_id] = change


def _send_order_change_confirmation(
    change: PendingOrderChange,
    telegram: TelegramBotApi,
) -> None:
    comparison = _format_order_change_comparison(change)
    telegram.send_message(
        change.chat_id,
        f"CONFIRMAR CAMBIO\n\n{comparison}\n\nLa confirmacion vence en 2 minutos.",
        reply_markup={
            "inline_keyboard": [
                [
                    {"text": "Confirmar", "callback_data": f"oc:{change.operation_id}:yes"},
                    {"text": "Cancelar", "callback_data": f"oc:{change.operation_id}:no"},
                ]
            ]
        },
    )


def _execute_order_revalidation(
    confirmation: PendingWorkerConfirmation,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    order_id = confirmation.command.removeprefix("revalidate:")
    try:
        current = admin_api.get_service_order(order_id)
        if str(current.get("preflight_status") or "") != "failed":
            telegram.send_message(
                confirmation.chat_id,
                "La orden cambio antes de confirmar y ya no requiere esa revalidacion.",
            )
            return
        admin_api.revalidate_service_order(
            order_id,
            actor=_telegram_actor(confirmation.chat_id),
        )
    except TelegramControlError as exc:
        logger.warning("Could not revalidate order from Telegram: %s", exc)
        telegram.send_message(
            confirmation.chat_id,
            "No pude iniciar la validacion. Revisa el estado y vuelve a intentarlo.",
        )
        return
    telegram.send_message(
        confirmation.chat_id,
        f"Validacion iniciada para {order_id}. Consulta el cliente en unos segundos.",
        reply_markup={
            "inline_keyboard": [[
                {"text": "Ver cliente", "callback_data": f"om:{order_id}:show"},
                {"text": "Menu", "callback_data": "ui:menu:main"},
            ]]
        },
    )


def _execute_order_change(
    change: PendingOrderChange,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    if change.action == "program_resolution":
        telegram_program_resolution.execute_resolution(
            change,
            telegram,
            admin_api,
            actor=_telegram_actor(change.chat_id),
            audit=_record_audit_safe,
            display_text=_display_text,
        )
        return
    operation_short = change.operation_id[:8]
    actor = _telegram_actor(change.chat_id)
    credentials_saved = False
    try:
        if change.action == "priority":
            current = admin_api.get_service_order(change.order_id)
            if int(current.get("priority") or 0) != int(change.original["priority"]):
                raise TelegramControlError(
                    "Order priority changed since the confirmation was prepared."
                )
            admin_api.update_order_priority(
                change.order_id,
                int(change.updated["priority"]),
                actor=actor,
            )
        elif change.action == "credentials":
            current = admin_api.get_service_order(change.order_id)
            current_details = current.get("preflight_details")
            current_error_type = (
                str(current_details.get("error_type") or "")
                if isinstance(current_details, dict)
                else ""
            )
            current_credentials = admin_api.get_service_order_credentials(change.order_id)
            current_password = str(current_credentials.get("password") or "")
            current_password_sha256 = hashlib.sha256(
                current_password.encode("utf-8")
            ).hexdigest()
            if (
                str(current.get("preflight_status") or "") != "failed"
                or current_error_type != "invalid_credentials"
                or int(current.get("preflight_cycle") or 0)
                != int(change.original["preflight_cycle"])
                or str(current_credentials.get("username") or "")
                != str(change.original["document_number"])
                or str(current_credentials.get("document_type") or "")
                != str(change.original["document_type"])
                or current_password_sha256 != change.original["password_sha256"]
            ):
                raise TelegramControlError(
                    "Order access changed since the confirmation was prepared."
                )
            admin_api.update_service_order_credentials(
                change.order_id,
                document_number=str(change.updated["document_number"]),
                document_type=str(change.updated["document_type"]),
                password=str(change.updated["password"]),
                actor=actor,
            )
            persisted_credentials = admin_api.get_service_order_credentials(change.order_id)
            if (
                str(persisted_credentials.get("username") or "")
                != str(change.updated["document_number"])
                or str(persisted_credentials.get("document_type") or "")
                != str(change.updated["document_type"])
                or str(persisted_credentials.get("password") or "")
                != str(change.updated["password"])
            ):
                raise TelegramControlError(
                    "Saved credentials do not match the requested change."
                )
            credentials_saved = True
        elif change.action in {"payment_paid", "payment_partial"}:
            current = admin_api.get_service_order(change.order_id)
            if (
                str(current.get("status") or "") != "reserved_payment_pending"
                or str(current.get("payment_status") or "") != "pending"
            ):
                raise TelegramControlError(
                    "Order is no longer a reservation with pending payment."
                )
            payment_method = (
                admin_api.record_partial_payment
                if change.action == "payment_partial"
                else admin_api.mark_payment_paid
            )
            payment_method(
                change.order_id,
                amount_paid=str(change.updated["amount_paid"]),
                amount_agreed=str(change.updated["amount_agreed"]),
                expected_amount_paid=str(change.original["amount_paid"]),
                actor=actor,
            )
        else:
            current = admin_api.get_service_order(change.order_id)
            if not all(
                current.get(field) == value
                for field, value in change.original.items()
            ):
                raise TelegramControlError(
                    "Order rules changed since the confirmation was prepared."
                )
            admin_api.update_order_rules(change.order_id, change.updated, actor=actor)
        verified = admin_api.get_service_order(change.order_id)
        if not _order_change_matches(change, verified):
            raise TelegramControlError("Saved order values do not match the requested change.")
        validation_text = ""
        if change.action == "credentials":
            verified = _wait_for_order_preflight(admin_api, change.order_id)
            preflight = str(verified.get("preflight_status") or "pending")
            if preflight == "validated":
                validation_text = "\nAcceso validado y cuenta activada."
            elif preflight == "failed":
                detail = verified.get("preflight_message") or "revisa el acceso"
                validation_text = f"\nEl nuevo acceso fue rechazado. Detalle: {detail}"
            else:
                validation_text = (
                    "\nLa nueva contrasena fue guardada. La validacion sigue en curso; "
                    "consulta el cliente en unos segundos."
                )
        elif (
            change.action == "rules"
            and str(verified.get("preflight_status") or "") != "validated"
        ):
            telegram.send_message(
                change.chat_id,
                "Restricciones guardadas. Validando ahora el acceso del cliente...",
            )
            admin_api.revalidate_service_order(change.order_id, actor=actor)
            verified = _wait_for_order_preflight(admin_api, change.order_id)
            preflight = str(verified.get("preflight_status") or "pendiente")
            if preflight == "validated":
                validation_text = "\nAcceso validado y orden activada."
            else:
                detail = verified.get("preflight_message") or "revisa el cliente"
                validation_text = f"\nValidacion: {preflight}. Detalle: {detail}"
        if change.action in {"payment_paid", "payment_partial"}:
            payment_result = (
                "Abono registrado y verificado.\nPostpago: no encolado; el cobro sigue pendiente."
                if change.action == "payment_partial"
                else "Pago registrado y verificado.\nPostpago: encolado automaticamente."
            )
            success_text = (
                f"{payment_result}\n"
                f"Solicitud: {operation_short}\n"
                f"Orden: {change.order_id}\n"
                f"Total pagado: S/{change.updated['amount_paid']}"
            )
            return_options = {
                "pending": ("Volver a pendientes", "ui:pending:1"),
                "payments": ("Volver a Por cobrar", "ui:payments:1"),
                "queue": ("Volver a Buscando cupo", "ui:queue:1"),
                "summary": ("Volver a Citas", "ui:summary:show"),
                "clients": ("Volver al historial", "ui:clients:1"),
            }
            return_label, return_callback = return_options.get(
                change.return_subject,
                ("Ver cobros pendientes", "ui:payments:1"),
            )
            success_keyboard = [
                [{"text": return_label, "callback_data": return_callback}],
                [
                    {"text": "Ver cliente", "callback_data": f"om:{change.order_id}:show"},
                    {"text": "Menu", "callback_data": "ui:menu:main"},
                ],
            ]
        else:
            success_text = (
                "Cambio aplicado y verificado.\n"
                f"Solicitud: {operation_short}\n"
                f"Orden: {change.order_id}"
                f"{validation_text}"
            )
            success_keyboard = [
                [
                    {"text": "Ver cliente", "callback_data": f"om:{change.order_id}:show"},
                    {"text": "Menu", "callback_data": "ui:menu:main"},
                ]
            ]
        telegram.send_message(
            change.chat_id,
            success_text,
            reply_markup={"inline_keyboard": success_keyboard},
        )
        logger.info(
            "Applied Telegram order change action=%s actor=%s order_id=%s",
            change.action,
            actor,
            change.order_id,
        )
        _record_audit_safe(
            actor=actor,
            action=change.action,
            status="applied",
            target_type="service_order",
            target_id=change.order_id,
            operation_id=change.operation_id,
        )
    except TelegramControlError as exc:
        logger.warning("Order change %s failed: %s", change.action, exc)
        if change.action == "credentials" and credentials_saved:
            telegram.send_message(
                change.chat_id,
                "La nueva contrasena fue guardada, pero no pude confirmar el resultado "
                "de la validacion. Abre nuevamente el cliente antes de intentar otro cambio.\n"
                f"Solicitud: {operation_short}\nOrden: {change.order_id}",
            )
            _record_audit_safe(
                actor=actor,
                action=change.action,
                status="applied",
                target_type="service_order",
                target_id=change.order_id,
                operation_id=change.operation_id,
                detail="Credentials saved; preflight follow-up could not be verified.",
            )
            return
        telegram.send_message(
            change.chat_id,
            f"No pude verificar la solicitud {operation_short}. No confirmo el cambio.",
        )
        _record_audit_safe(
            actor=actor,
            action=change.action,
            status="failed",
            target_type="service_order",
            target_id=change.order_id,
            operation_id=change.operation_id,
            detail="Admin API action could not be verified.",
        )
    except Exception:
        logger.exception("Unexpected order change execution failure")


def _order_change_matches(change: PendingOrderChange, order: dict[str, Any]) -> bool:
    if change.action == "credentials":
        return (
            int(order.get("preflight_cycle") or 0)
            > int(change.original.get("preflight_cycle") or 0)
            and str(order.get("preflight_status") or "")
            in {"pending", "running", "validated", "failed"}
        )
    if change.action == "payment_partial":
        return (
            str(order.get("status") or "") == "reserved_payment_pending"
            and str(order.get("payment_status") or "") == "pending"
            and _money_value(order.get("amount_paid"))
            == _money_value(change.updated.get("amount_paid"))
            and _money_value(order.get("amount_agreed"))
            == _money_value(change.updated.get("amount_agreed"))
        )
    if change.action == "payment_paid":
        return (
            str(order.get("status") or "") == "paid"
            and str(order.get("payment_status") or "") == "paid"
            and _money_value(order.get("amount_paid"))
            == _money_value(change.updated.get("amount_paid"))
            and _money_value(order.get("amount_agreed"))
            == _money_value(change.updated.get("amount_agreed"))
        )
    return all(order.get(field) == value for field, value in change.updated.items())
