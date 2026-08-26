from __future__ import annotations

import re
from dataclasses import dataclass

from appointment_bot.utils.sanitization import sanitize_text

MAX_TEMPLATE_LENGTH = 1500
MAX_RENDERED_LENGTH = 4096
MAX_VARIABLE_REPETITIONS = 10

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_SAFE_UNSANITIZED_VARIABLES = frozenset(
    {"numero_pago", "titular_pago", "usuario_tiktok"}
)


@dataclass(frozen=True)
class WhatsAppTemplateDefinition:
    key: str
    display_name: str
    current_default_template: str
    recommended_template: str
    allowed_variables: tuple[str, ...]
    required_variables: tuple[str, ...]
    optional_line_variables: tuple[str, ...]
    usage: str
    applies_from: str
    preview_context: dict[str, str]


_REGISTRATION_MONITORING_STARTED = "\n\n".join(
    (
        "Hola, {nombre} 👋",
        "Pudimos ingresar correctamente y verificar tu solicitud ✅",
        "Tu solicitud quedó registrada y desde ahora comenzaremos con el monitoreo.",
        "Servicio: {servicio}\nPrecio acordado: S/{monto}\n"
        "Condiciones de búsqueda: {condiciones}\n{fechas_excluidas}",
        "Buscaremos únicamente citas que cumplan estas condiciones. "
        "No reservaremos una fecha fuera de ellas.",
        "La disponibilidad depende de la PNP y no podemos garantizar que "
        "aparezca un cupo. Te escribiremos apenas consigamos la cita.",
    )
)

_REGISTRATION_NO_PENDING_REQUEST = "\n\n".join(
    (
        "Hola, {nombre} 👋",
        "Pudimos ingresar correctamente, pero no encontramos una solicitud "
        "pendiente para reservar.",
        "Por favor, revisa si el trámite fue registrado y confírmanos cuando "
        "aparezca. Luego realizaremos una nueva validación.",
    )
)

_REGISTRATION_INVALID_CREDENTIALS = "\n\n".join(
    (
        "Hola, {nombre} 👋",
        "No pudimos validar el acceso con los datos registrados.",
        "Por seguridad realizamos un solo intento para evitar el bloqueo "
        "temporal de tu cuenta.",
        "Por favor, revisa el tipo y número de documento y la contraseña, y "
        "confírmanos los datos correctos para volver a validar.",
    )
)

_RESERVATION_CONFIRMATION = """Estimado/a {nombre}, su cita ha sido reservada con exito.

Fecha: {fecha}
Hora: {hora}
Sede: {sede}"""

_RESERVATION_PAYMENT = (
    "Ahora ya podemos proceder con el pago del servicio, el monto es de "
    "{monto} soles.\nEl número es {numero_pago} a nombre de *{titular_pago}*"
)

_POST_PAYMENT_CONFIRMATION = "\n\n".join(
    (
        "✅ *¡Pago confirmado!*\n"
        "Cita reservada. Llegue 30 min antes y vaya con el vehículo ya polarizado.\n"
        "Reserva: {fecha} {hora}\nSede: {sede}",
        "📄 Lleve los PDFs adjuntos impresos, llenados y firmados. "
        "Revise requisitos y copias.",
        "🔍 El peritaje dura aprox. 5 min. Después de pasarlo, en 2 días "
        "consulte su autorización virtual en la misma web de reserva.",
        "Gracias por confiar en nosotros. Si puede dejarnos un comentario en "
        "TikTok nos ayuda muchísimo: {usuario_tiktok}",
    )
)

_CURRENT_APPOINTMENT_REMINDER = "\n\n".join(
    (
        "Hola, {nombre} 👋",
        "Como parte de nuestro servicio, te enviamos un recordatorio de tu cita "
        "para el trámite de lunas polarizadas:",
        "📅 *Fecha:* {fecha}\n🕐 *Hora:* {hora}\n📍 *Sede:* {sede}",
        "Recuerda asistir con anticipación y llevar la documentación necesaria "
        "para tu trámite.",
        "¡Éxitos en tu cita! 😊",
    )
)

_RECOMMENDED_APPOINTMENT_REMINDER = (
    "Hola, {nombre}. Te recordamos que mañana, {fecha}, tienes tu cita de "
    "lunas polarizadas. Hora: {hora}. Sede: {sede}. Si tu cita fue modificada "
    "recientemente, por favor comunícate con nosotros."
)

_COMMON_PREVIEW_CONTEXT = {
    "nombre": "Carlos",
    "servicio": "Día elegido",
    "monto": "70.00",
    "monto_pagado": "70.00",
    "fecha": "06/09/2026",
    "hora": "10:30",
    "sede": "MAC Lima Norte",
    "condiciones": "Solo los sábados, desde el 01/09/2026 hasta el 31/10/2026.",
    "fechas_excluidas": "Fechas excluidas: 12/09/2026",
    "numero_pago": "999 999 999",
    "titular_pago": "Citas Polarizadas Perú",
    "usuario_tiktok": "@citaspolarizadasperu",
}


def _definition(
    key: str,
    display_name: str,
    template: str,
    allowed_variables: tuple[str, ...],
    required_variables: tuple[str, ...],
    usage: str,
    applies_from: str,
    *,
    recommended_template: str | None = None,
    optional_line_variables: tuple[str, ...] = (),
) -> WhatsAppTemplateDefinition:
    return WhatsAppTemplateDefinition(
        key=key,
        display_name=display_name,
        current_default_template=template,
        recommended_template=recommended_template or template,
        allowed_variables=allowed_variables,
        required_variables=required_variables,
        optional_line_variables=optional_line_variables,
        usage=usage,
        applies_from=applies_from,
        preview_context={name: _COMMON_PREVIEW_CONTEXT[name] for name in allowed_variables},
    )


WHATSAPP_TEMPLATE_DEFINITIONS = {
    definition.key: definition
    for definition in (
        _definition(
            "registration_monitoring_started",
            "Registro validado e inicio de monitoreo",
            _REGISTRATION_MONITORING_STARTED,
            ("nombre", "servicio", "monto", "condiciones", "fechas_excluidas"),
            ("nombre", "servicio", "monto", "condiciones"),
            "Aviso de registro validado enviado después del preflight.",
            "next_prepared_job",
            optional_line_variables=("fechas_excluidas",),
        ),
        _definition(
            "registration_no_pending_request",
            "Acceso correcto sin solicitud pendiente",
            _REGISTRATION_NO_PENDING_REQUEST,
            ("nombre",),
            ("nombre",),
            "Aviso del preflight cuando el portal no muestra una solicitud pendiente.",
            "next_prepared_job",
        ),
        _definition(
            "registration_invalid_credentials",
            "Credenciales rechazadas",
            _REGISTRATION_INVALID_CREDENTIALS,
            ("nombre",),
            ("nombre",),
            "Aviso del preflight después del único intento de acceso rechazado.",
            "next_prepared_job",
        ),
        _definition(
            "reservation_confirmation",
            "Reserva confirmada",
            _RESERVATION_CONFIRMATION,
            ("nombre", "fecha", "hora", "sede"),
            ("nombre", "fecha", "hora", "sede"),
            "Confirmación incluida en el paquete preparado después de reservar.",
            "next_prepared_message",
        ),
        _definition(
            "reservation_payment",
            "Instrucciones de pago",
            _RESERVATION_PAYMENT,
            ("monto", "numero_pago", "titular_pago"),
            ("monto", "numero_pago", "titular_pago"),
            "Cobro incluido en el paquete preparado después de reservar.",
            "next_prepared_message",
        ),
        _definition(
            "post_payment_confirmation",
            "Pago confirmado",
            _POST_PAYMENT_CONFIRMATION,
            ("nombre", "fecha", "hora", "sede", "monto_pagado", "usuario_tiktok"),
            ("fecha", "hora", "sede", "usuario_tiktok"),
            "Texto compacto enviado después de los documentos de postpago.",
            "next_prepared_followup",
        ),
        _definition(
            "appointment_reminder",
            "Recordatorio pre-cita",
            _CURRENT_APPOINTMENT_REMINDER,
            ("nombre", "fecha", "hora", "sede"),
            ("fecha",),
            "Recordatorio existente; su control operativo permanece separado.",
            "next_reconciliation",
            recommended_template=_RECOMMENDED_APPOINTMENT_REMINDER,
        ),
    )
}


def normalize_template(message_template: str) -> str:
    return message_template.replace("\r\n", "\n").replace("\r", "\n").strip()


def validate_whatsapp_template(
    definition: WhatsAppTemplateDefinition,
    message_template: str,
) -> dict[str, str]:
    template = normalize_template(message_template)
    if not template:
        return {"message_template": "El mensaje no puede quedar vacío."}
    errors: dict[str, str] = {}
    if len(template) > MAX_TEMPLATE_LENGTH:
        errors["message_template"] = (
            f"El mensaje no puede superar {MAX_TEMPLATE_LENGTH} caracteres."
        )
    if any(ord(character) < 32 and character not in {"\n", "\t"} for character in template):
        errors["message_template"] = "El mensaje contiene caracteres de control no permitidos."
    placeholders = _PLACEHOLDER.findall(template)
    stripped = _PLACEHOLDER.sub("", template)
    if "{" in stripped or "}" in stripped:
        errors["message_template"] = "Hay una variable incompleta o llaves sin cerrar."
    unknown = sorted(set(placeholders) - set(definition.allowed_variables))
    if unknown:
        errors["message_template"] = "Variables no permitidas: " + ", ".join(
            "{" + name + "}" for name in unknown
        )
    missing = [name for name in definition.required_variables if name not in placeholders]
    if missing:
        errors["message_template"] = "Faltan variables obligatorias: " + ", ".join(
            "{" + name + "}" for name in missing
        )
    repeated = sorted(
        name
        for name in set(placeholders)
        if placeholders.count(name) > MAX_VARIABLE_REPETITIONS
    )
    if repeated:
        errors["message_template"] = "Hay variables repetidas demasiadas veces: " + ", ".join(
            "{" + name + "}" for name in repeated
        )
    return errors


def render_whatsapp_template(
    definition: WhatsAppTemplateDefinition,
    message_template: str,
    context: dict[str, object],
) -> str:
    template = normalize_template(message_template)
    errors = validate_whatsapp_template(definition, template)
    if errors:
        raise ValueError(errors["message_template"])
    lines = template.split("\n")
    for variable in definition.optional_line_variables:
        value = str(context.get(variable) or "").strip()
        placeholder = "{" + variable + "}"
        if not value:
            lines = [line for line in lines if line.strip() != placeholder]
    rendered = "\n".join(lines)

    def replacement(match: re.Match[str]) -> str:
        variable = match.group(1)
        if variable not in context:
            raise ValueError(f"Falta un valor para {{{variable}}}.")
        value = str(context.get(variable) or "").strip()
        if not value:
            raise ValueError(f"El valor de {{{variable}}} no puede quedar vacío.")
        if variable not in _SAFE_UNSANITIZED_VARIABLES:
            value = sanitize_text(value)
        return value

    rendered = _PLACEHOLDER.sub(replacement, rendered)
    rendered = rendered.strip()
    if not rendered:
        raise ValueError("El mensaje renderizado no puede quedar vacío.")
    if len(rendered) > MAX_RENDERED_LENGTH:
        raise ValueError(
            f"El mensaje renderizado no puede superar {MAX_RENDERED_LENGTH} caracteres."
        )
    return rendered


def whatsapp_template_definition(template_key: str) -> WhatsAppTemplateDefinition | None:
    return WHATSAPP_TEMPLATE_DEFINITIONS.get(template_key.strip())


__all__ = [
    "MAX_RENDERED_LENGTH",
    "MAX_TEMPLATE_LENGTH",
    "WHATSAPP_TEMPLATE_DEFINITIONS",
    "WhatsAppTemplateDefinition",
    "normalize_template",
    "render_whatsapp_template",
    "validate_whatsapp_template",
    "whatsapp_template_definition",
]
