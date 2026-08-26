from __future__ import annotations

import logging
from http import HTTPStatus

from appointment_bot.config import load_settings
from appointment_bot.core.whatsapp_message_templates import (
    WHATSAPP_TEMPLATE_DEFINITIONS,
    normalize_template,
    render_whatsapp_template,
    validate_whatsapp_template,
    whatsapp_template_definition,
)
from appointment_bot.db.whatsapp_message_templates import (
    WhatsAppMessageTemplate,
    WhatsAppMessageTemplateConflict,
    get_whatsapp_message_template,
    list_whatsapp_message_templates,
    update_whatsapp_message_template,
)
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.registration_notices import (
    REGISTRATION_NOTICE_TEMPLATE_KEYS,
)
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)

_COLLECTION_PATH = "/api/v1/whatsapp-message-templates"


def whatsapp_message_template_action_path(path: str, action: str | None = None) -> str | None:
    prefix = _COLLECTION_PATH + "/"
    if not path.startswith(prefix):
        return None
    remainder = path.removeprefix(prefix)
    if action is None:
        return remainder if remainder and "/" not in remainder else None
    suffix = "/" + action
    if not remainder.endswith(suffix):
        return None
    template_key = remainder[: -len(suffix)]
    return template_key if template_key and "/" not in template_key else None


def whatsapp_message_templates_payload() -> tuple[HTTPStatus, dict[str, object]]:
    try:
        settings = load_settings(require_login=False)
        rows = {
            item.template_key: item for item in list_whatsapp_message_templates(settings)
        }
        expected_keys = set(WHATSAPP_TEMPLATE_DEFINITIONS)
        if set(rows) != expected_keys:
            missing = sorted(expected_keys - set(rows))
            unexpected = sorted(set(rows) - expected_keys)
            raise RuntimeError(
                "WhatsApp template registry is inconsistent: "
                f"missing={missing}; unexpected={unexpected}."
            )
        templates = [
            _template_payload(rows[key])
            for key in WHATSAPP_TEMPLATE_DEFINITIONS
            if key in rows
        ]
        return HTTPStatus.OK, {"status": "ok", "templates": templates}
    except (RuntimeError, ValueError) as exc:
        logger.exception("Could not list WhatsApp message templates")
        return HTTPStatus.BAD_REQUEST, error_payload(
            "whatsapp_message_templates_unavailable",
            sanitize_text(str(exc)),
        )


def preview_whatsapp_message_template_payload(
    template_key: str,
    body: dict[str, object],
) -> tuple[HTTPStatus, dict[str, object]]:
    definition = whatsapp_template_definition(template_key)
    if definition is None:
        return HTTPStatus.NOT_FOUND, error_payload(
            "not_found", "La plantilla de WhatsApp no existe."
        )
    raw_template = body.get("message_template")
    if not isinstance(raw_template, str):
        message_template = ""
        errors = {"message_template": "El mensaje debe ser texto."}
    else:
        message_template = normalize_template(raw_template)
        errors = validate_whatsapp_template(definition, message_template)
    if errors:
        payload = error_payload("bad_request", "Revisa el contenido de la plantilla.")
        payload["field_errors"] = errors
        return HTTPStatus.BAD_REQUEST, payload
    try:
        preview = render_whatsapp_template(
            definition,
            message_template,
            definition.preview_context,
        )
    except ValueError as exc:
        payload = error_payload("bad_request", "No se pudo renderizar la plantilla.")
        payload["field_errors"] = {"message_template": str(exc)}
        return HTTPStatus.BAD_REQUEST, payload
    return HTTPStatus.OK, {
        "status": "ok",
        "template_key": definition.key,
        "preview": preview,
        "preview_context": dict(definition.preview_context),
        "persists": False,
        "sends_message": False,
    }


def update_whatsapp_message_template_payload(
    template_key: str,
    body: dict[str, object],
    *,
    requested_by: str | None,
) -> tuple[HTTPStatus, dict[str, object]]:
    definition = whatsapp_template_definition(template_key)
    if definition is None:
        return HTTPStatus.NOT_FOUND, error_payload(
            "not_found", "La plantilla de WhatsApp no existe."
        )
    raw_template = body.get("message_template")
    expected_revision = body.get("expected_revision")
    if not isinstance(raw_template, str):
        message_template = ""
        errors = {"message_template": "El mensaje debe ser texto."}
    else:
        message_template = normalize_template(raw_template)
        errors = validate_whatsapp_template(definition, message_template)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        errors["expected_revision"] = "La revisión esperada debe ser un entero."
    elif expected_revision < 1:
        errors["expected_revision"] = "La revisión esperada debe ser mayor que cero."
    if errors:
        payload = error_payload("bad_request", "Revisa el contenido de la plantilla.")
        payload["field_errors"] = errors
        return HTTPStatus.BAD_REQUEST, payload
    settings = load_settings(require_login=False)
    try:
        updated = update_whatsapp_message_template(
            template_key=definition.key,
            message_template=message_template,
            expected_revision=int(expected_revision),
            updated_by=requested_by or "dashboard-owner",
            settings=settings,
        )
    except WhatsAppMessageTemplateConflict as exc:
        current = get_whatsapp_message_template(definition.key, settings)
        payload = error_payload("stale", str(exc))
        if current is not None:
            payload["current"] = _template_payload(current)
        return HTTPStatus.CONFLICT, payload
    return HTTPStatus.OK, _template_payload(updated)


def _template_payload(row: WhatsAppMessageTemplate) -> dict[str, object]:
    definition = WHATSAPP_TEMPLATE_DEFINITIONS[row.template_key]
    preview = render_whatsapp_template(
        definition,
        row.message_template,
        definition.preview_context,
    )
    return {
        "status": "ok",
        "template_key": row.template_key,
        "display_name": definition.display_name,
        "message_template": row.message_template,
        "recommended_template": definition.recommended_template,
        "allowed_variables": ["{" + name + "}" for name in definition.allowed_variables],
        "required_variables": ["{" + name + "}" for name in definition.required_variables],
        "optional_line_variables": [
            "{" + name + "}" for name in definition.optional_line_variables
        ],
        "revision": row.revision,
        "enabled": row.enabled,
        "updated_at": row.updated_at.isoformat(),
        "updated_by": row.updated_by,
        "preview": preview,
        "preview_context": dict(definition.preview_context),
        "usage": definition.usage,
        "applies_from": definition.applies_from,
        "consumer_connected": row.template_key
        in REGISTRATION_NOTICE_TEMPLATE_KEYS.values(),
    }


__all__ = [
    "preview_whatsapp_message_template_payload",
    "update_whatsapp_message_template_payload",
    "whatsapp_message_template_action_path",
    "whatsapp_message_templates_payload",
]
