from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from appointment_bot.core.contacts import (
    ContactValidationError,
    normalize_contact_whatsapp,
    normalize_contact_whatsapp_username,
)
from appointment_bot.core.service_packages import (
    SERVICE_PACKAGE_CUSTOM,
    SERVICE_PACKAGE_INTEGRAL,
    SERVICE_PACKAGE_RESTRICTED,
    SERVICE_PACKAGE_STANDARD,
    money_text,
    service_package_definition,
)
from appointment_bot.services.telegram.constants import NEW_CLIENT_CONVERSATION_TTL_SECONDS
from appointment_bot.services.telegram.models import NewClientConversation
from appointment_bot.services.telegram.presentation import _money_text
from appointment_bot.services.telegram.validation import (
    _parse_rules_step,
    _parse_single_weekday,
    _validate_rules_payload,
    _validated_payment_amount,
)


def _telegram_service_package_option(package_key: str) -> str:
    definition = service_package_definition(package_key)
    amount = money_text(definition.total_amount)
    return definition.label if amount is None else f"{definition.label} - S/{amount}"


def _new_client_prompt_markup(conversation: NewClientConversation) -> dict[str, Any]:
    step = conversation.step
    session_id = conversation.session_id
    if step == 0:
        keyboard = [[
            {"text": "DNI", "callback_data": f"nf:{session_id}:type_dni"},
            {"text": "CE", "callback_data": f"nf:{session_id}:type_ce"},
        ]]
    elif step == 4:
        keyboard = [
            [
                {"text": "TikTok", "callback_data": f"nf:{session_id}:source_tiktok"},
                {"text": "Facebook", "callback_data": f"nf:{session_id}:source_facebook"},
            ],
            [{"text": "WhatsApp", "callback_data": f"nf:{session_id}:source_whatsapp"}],
        ]
    elif step == 5:
        keyboard = [
            [
                {
                    "text": "Numero",
                    "callback_data": f"nf:{session_id}:phone_number",
                },
                {
                    "text": "Usuario",
                    "callback_data": f"nf:{session_id}:phone_username",
                },
            ],
            [
                {
                    "text": "Omitir WhatsApp",
                    "callback_data": f"nf:{session_id}:phone_omit",
                }
            ],
        ]
    elif step == 6:
        keyboard = [
            [{
                "text": _telegram_service_package_option(SERVICE_PACKAGE_STANDARD),
                "callback_data": f"nf:{session_id}:service_standard",
            }],
            [{
                "text": _telegram_service_package_option(SERVICE_PACKAGE_RESTRICTED),
                "callback_data": f"nf:{session_id}:service_weekday",
            }],
            [{
                "text": _telegram_service_package_option(SERVICE_PACKAGE_INTEGRAL),
                "callback_data": f"nf:{session_id}:service_integral",
            }],
            [{
                "text": _telegram_service_package_option(SERVICE_PACKAGE_CUSTOM),
                "callback_data": f"nf:{session_id}:service_custom",
            }],
        ]
    elif step == 8:
        keyboard = [
            [
                {"text": "Lunes", "callback_data": f"nf:{session_id}:weekday_1"},
                {"text": "Martes", "callback_data": f"nf:{session_id}:weekday_2"},
            ],
            [
                {"text": "Miercoles", "callback_data": f"nf:{session_id}:weekday_3"},
                {"text": "Jueves", "callback_data": f"nf:{session_id}:weekday_4"},
            ],
            [
                {"text": "Viernes", "callback_data": f"nf:{session_id}:weekday_5"},
                {"text": "Sabado", "callback_data": f"nf:{session_id}:weekday_6"},
            ],
            [{"text": "Domingo", "callback_data": f"nf:{session_id}:weekday_7"}],
        ]
    elif step == 9:
        keyboard = [[
            {"text": "Sin restricciones", "callback_data": f"nf:{session_id}:rules_none"},
            {"text": "Configurar", "callback_data": f"nf:{session_id}:rules_yes"},
        ]]
    elif step in {10, 11}:
        keyboard = [[{
            "text": "Sin limite",
            "callback_data": f"nf:{session_id}:value_clear",
        }]]
    elif step == 12:
        keyboard = [
            [
                {"text": "Lun-Vie", "callback_data": f"nf:{session_id}:days_mon_fri"},
                {"text": "Lun-Sab", "callback_data": f"nf:{session_id}:days_mon_sat"},
            ],
            [
                {"text": "Solo sabado", "callback_data": f"nf:{session_id}:days_sat"},
                {"text": "Todos", "callback_data": f"nf:{session_id}:value_clear"},
            ],
        ]
    elif step == 13:
        keyboard = [[{
            "text": "Sin exclusiones",
            "callback_data": f"nf:{session_id}:value_clear",
        }]]
    else:
        keyboard = []
    if step > 0:
        keyboard.append([{"text": "Atras", "callback_data": f"nf:{session_id}:back"}])
    keyboard.append([{"text": "Cancelar", "callback_data": "ui:cancel:guided"}])
    return {"inline_keyboard": keyboard}


def _rewind_new_client(conversation: NewClientConversation) -> str:
    if conversation.step == 5 and conversation.values.pop("_whatsapp_recipient_mode", None):
        return _manual_client_step_prompt(5) or "Elige el tipo de WhatsApp."
    if conversation.step in {7, 8}:
        target_step = 6
    elif conversation.step == 9:
        target_step = 7 if conversation.values.get("service_type") == "custom" else 6
    elif (
        conversation.step == 13
        and conversation.values.get("service_type") == "selected_weekday"
    ):
        target_step = 11
    else:
        target_step = max(0, conversation.step - 1)
    fields_by_step = {
        0: ("document_type",),
        1: ("document_number",),
        2: ("password",),
        3: ("contact_name",),
        4: ("contact_source",),
        5: ("contact_whatsapp", "contact_whatsapp_username", "_whatsapp_recipient_mode"),
        6: ("service_type", "service_package", "reservation_price"),
        7: ("reservation_price",),
        8: (
            "minimum_reservation_date",
            "maximum_reservation_date",
            "allowed_weekdays",
            "excluded_date_ranges",
        ),
        9: (
            "minimum_reservation_date",
            "maximum_reservation_date",
            "allowed_weekdays",
            "excluded_date_ranges",
        ),
        10: ("minimum_reservation_date",),
        11: ("maximum_reservation_date",),
        12: ("allowed_weekdays",),
        13: ("excluded_date_ranges",),
    }
    for field_name in fields_by_step.get(target_step, ()):
        conversation.values.pop(field_name, None)
    conversation.step = target_step
    conversation.expires_at = time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS
    return (
        "Paso 1: elige el tipo de documento."
        if target_step == 0
        else _manual_client_step_prompt(target_step) or "Revisa el paso anterior."
    )


def _apply_new_client_value(
    conversation: NewClientConversation, value: str
) -> str | None:
    return _apply_manual_client_value(conversation, value)


def _fixed_service_package_values(
    package_key: str,
    *,
    service_type: str | None = None,
) -> dict[str, str]:
    definition = service_package_definition(package_key)
    reservation_price = money_text(definition.total_amount)
    if reservation_price is None:
        raise ValueError(f"El paquete {package_key} exige un monto manual.")
    return {
        "service_type": service_type or definition.default_service_type,
        "service_package": definition.key,
        "reservation_price": reservation_price,
    }


def _apply_manual_client_value(
    conversation: NewClientConversation,
    value: str,
) -> str | None:
    step = conversation.step
    normalized = value.strip()
    if step == 0:
        document_types = {
            "dni": "dni",
            "ce": "foreign_resident_card",
            "foreign_resident_card": "foreign_resident_card",
        }
        document_type = document_types.get(normalized.lower())
        if document_type is None:
            raise ValueError("Elige DNI o CE.")
        conversation.values["document_type"] = document_type
    elif step == 1:
        document_number = re.sub(r"\s", "", normalized)
        if conversation.values.get("document_type") == "dni":
            if not re.fullmatch(r"\d{8}", document_number):
                raise ValueError("El DNI debe tener exactamente 8 digitos.")
        elif not re.fullmatch(r"[A-Za-z0-9]{6,20}", document_number):
            raise ValueError("El CE debe tener entre 6 y 20 letras o numeros.")
        conversation.values["document_number"] = document_number
    elif step == 2:
        if not normalized or len(value) > 200:
            raise ValueError("La contrasena debe tener entre 1 y 200 caracteres.")
        conversation.values["password"] = value
    elif step == 3:
        contact_name = " ".join(normalized.split())
        if not 2 <= len(contact_name) <= 100:
            raise ValueError("El nombre de contacto debe tener entre 2 y 100 caracteres.")
        conversation.values["contact_name"] = contact_name
    elif step == 4:
        source = normalized.lower()
        if source not in {"tiktok", "facebook", "whatsapp"}:
            raise ValueError("Elige TikTok, Facebook o WhatsApp.")
        conversation.values["contact_source"] = source
    elif step == 5:
        mode = conversation.values.get("_whatsapp_recipient_mode")
        choice = normalized.casefold().replace(" ", "_")
        if mode is None:
            if choice in {"numero", "número", "whatsapp_numero"}:
                conversation.values["_whatsapp_recipient_mode"] = "phone"
                return "Paso 6: escribe el numero de WhatsApp."
            if choice in {"usuario", "whatsapp_usuario"}:
                conversation.values["_whatsapp_recipient_mode"] = "username"
                return "Paso 6: escribe el usuario de WhatsApp, con o sin @."
            if choice not in {"omitir", "sin_whatsapp"}:
                raise ValueError("Elige Numero, Usuario u Omitir WhatsApp.")
        else:
            try:
                if mode == "phone":
                    if not normalized:
                        raise ValueError("Escribe el numero de WhatsApp.")
                    conversation.values["contact_whatsapp"] = (
                        normalize_contact_whatsapp(normalized)
                    )
                else:
                    username = unicodedata.normalize("NFKC", normalized)
                    username = "".join(
                        character
                        for character in username
                        if unicodedata.category(character) != "Cf"
                    ).strip()
                    username = f"@{username.lstrip('@')}"
                    conversation.values["contact_whatsapp_username"] = (
                        normalize_contact_whatsapp_username(username)
                    )
            except ContactValidationError as exc:
                raise ValueError(str(exc)) from exc
            finally:
                if "contact_whatsapp" in conversation.values or (
                    "contact_whatsapp_username" in conversation.values
                ):
                    conversation.values.pop("_whatsapp_recipient_mode", None)
    elif step == 6:
        choice = normalized.casefold().replace(" ", "_")
        if choice in {"servicio_estandar", "estandar", "estándar"}:
            conversation.values.update(
                _fixed_service_package_values(SERVICE_PACKAGE_STANDARD)
            )
            conversation.step = 8
        elif choice in {"servicio_dia_elegido", "dia_elegido", "día_elegido"}:
            conversation.values.update(
                _fixed_service_package_values(
                    SERVICE_PACKAGE_RESTRICTED,
                    service_type="selected_weekday",
                )
            )
            conversation.step = 7
        elif choice in {"servicio_integral", "tramite_integral", "trámite_integral"}:
            conversation.values.update(
                _fixed_service_package_values(SERVICE_PACKAGE_INTEGRAL)
            )
            conversation.step = 8
        elif choice in {"servicio_personalizado", "personalizado"}:
            custom = service_package_definition(SERVICE_PACKAGE_CUSTOM)
            conversation.values.update(
                {
                    "service_type": custom.default_service_type,
                    "service_package": custom.key,
                }
            )
        else:
            raise ValueError(
                "Elige Estandar, Dia elegido, Tramite integral o Monto personalizado."
            )
    elif step == 7:
        if conversation.values.get("service_type") != "custom":
            raise ValueError("El monto manual solo corresponde al servicio personalizado.")
        conversation.values["reservation_price"] = _money_text(
            _validated_payment_amount(normalized)
        )
        conversation.step = 8
    elif step == 8:
        if conversation.values.get("service_type") != "selected_weekday":
            raise ValueError("El dia solo corresponde al servicio Dia elegido.")
        selected_weekday = _parse_single_weekday(normalized)
        conversation.values.update(
            {
                "minimum_reservation_date": None,
                "maximum_reservation_date": None,
                "allowed_weekdays": [selected_weekday],
                "excluded_date_ranges": [],
            }
        )
    elif step == 9:
        choice = normalized.lower().replace(" ", "_")
        if choice == "sin_restricciones":
            conversation.step = 13
            return None
        if choice not in {"con_restricciones", "configurar"}:
            raise ValueError("Elige Sin restricciones o Configurar.")
        conversation.values.update(
            {
                "minimum_reservation_date": None,
                "maximum_reservation_date": None,
                "allowed_weekdays": (
                    conversation.values.get("allowed_weekdays")
                    if conversation.values.get("service_type") == "selected_weekday"
                    else None
                ),
                "excluded_date_ranges": [],
            }
        )
    else:
        field, parsed_value = _parse_rules_step(step - 10, normalized, conversation.values)
        conversation.values[field] = parsed_value
        if step == 11:
            _validate_rules_payload(conversation.values)
            if conversation.values.get("service_type") == "selected_weekday":
                conversation.step = 12
        if step == 13:
            _validate_rules_payload(conversation.values)
    conversation.step += 1
    return _manual_client_step_prompt(conversation.step)


def _manual_client_step_prompt(step: int) -> str | None:
    prompts = {
        1: "Paso 2: escribe el numero de documento.",
        2: "Paso 3: escribe la contrasena del portal.",
        3: "Paso 4: escribe el nombre de la persona de contacto.",
        4: "Paso 5: elige de donde llego el cliente.",
        5: "Paso 6: elige si registrarás un numero o un usuario de WhatsApp.",
        6: "Paso 7: elige el servicio y precio acordados.",
        7: "Paso 8: escribe el monto personalizado total en soles.",
        8: "Paso 8: elige un dia de la semana para buscar siempre ese dia.",
        9: "Paso 8: indica si deseas configurar restricciones ahora.",
        10: "Fecha minima: escribe DD-MM-YYYY o elige Sin limite.",
        11: "Fecha maxima: escribe DD-MM-YYYY o elige Sin limite.",
        12: "Dias permitidos: elige una opcion o escribe 1,2,...7.",
        13: (
            "Fechas excluidas en DD-MM-YYYY al DD-MM-YYYY; "
            "separa varios rangos con ; o elige Sin exclusiones."
        ),
    }
    return prompts.get(step)
