from __future__ import annotations

from datetime import date, datetime
from http import HTTPStatus
from typing import Any

from appointment_bot.db.hosted_registrations import (
    attach_invitation,
    create_registration_contact,
    get_registration_contact,
    list_registration_contacts,
    replace_invitation,
    update_registration_contact_name,
)
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.hosted_registration_client import (
    HostedRegistrationClient,
    HostedRegistrationError,
)


def list_hosted_invitations_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    local_rows = list_registration_contacts()
    try:
        hosted_rows = HostedRegistrationClient.operator().list_invitations()
    except HostedRegistrationError as exc:
        return HTTPStatus(exc.status), error_payload(exc.code, str(exc))
    hosted_by_ref: dict[str, dict[str, Any]] = {}
    for row in hosted_rows:
        contact_ref = str(row.get("contact_ref") or "")
        if contact_ref and contact_ref not in hosted_by_ref:
            hosted_by_ref[contact_ref] = row
    items = []
    for row in local_rows:
        hosted = hosted_by_ref.get(str(row["contact_ref"]), {})
        local_state = str(row["state"])
        displayed_status = (
            local_state
            if local_state
            not in {"local_pending", "issued", "opened", "submitted", "revoked", "expired"}
            else hosted.get("status") or local_state
        )
        items.append(
            {
                "contact_ref": row["contact_ref"],
                "display_name": row["display_name"],
                "whatsapp_phone": row["whatsapp_phone"],
                "phone_hint": _phone_hint(str(row["whatsapp_phone"])),
                "invitation_id": hosted.get("invitation_id") or row.get("invitation_id"),
                "request_id": row.get("request_id"),
                "order_id": row.get("order_id"),
                "status": displayed_status,
                "availability_mode": row.get("availability_mode"),
                "expires_at": hosted.get("expires_at"),
                "created_at": _json_value(row["created_at"]),
                "updated_at": _json_value(row["updated_at"]),
            }
        )
    return HTTPStatus.OK, {"invitations": items}


def create_hosted_invitation_payload(
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    phone = str(payload.get("whatsapp_phone") or "").strip()
    display_name = str(payload.get("display_name") or "").strip()
    if not phone:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            "El WhatsApp es obligatorio.",
        )
    try:
        local = create_registration_contact(
            whatsapp_phone=phone,
            display_name=display_name,
        )
        invitation = HostedRegistrationClient.operator().create_invitation(
            str(local["contact_ref"]),
            _phone_hint(str(local["whatsapp_phone"])),
        )
        attach_invitation(
            str(local["contact_ref"]),
            str(invitation["invitation_id"]),
        )
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, error_payload("bad_request", str(exc))
    except HostedRegistrationError as exc:
        return HTTPStatus(exc.status), error_payload(exc.code, str(exc))
    return HTTPStatus.CREATED, {
        "status": "issued",
        "contact_ref": local["contact_ref"],
        "display_name": local["display_name"],
        "whatsapp_phone": local["whatsapp_phone"],
        **invitation,
    }


def revoke_hosted_invitation_payload(
    invitation_id: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        result = HostedRegistrationClient.operator().revoke_invitation(invitation_id)
    except HostedRegistrationError as exc:
        return HTTPStatus(exc.status), error_payload(exc.code, str(exc))
    return HTTPStatus.OK, result


def reissue_hosted_invitation_payload(
    invitation_id: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        client = HostedRegistrationClient.operator()
        hosted = client.get_invitation(invitation_id)
        contact_ref = str(hosted.get("contact_ref") or "")
        if not contact_ref or get_registration_contact(contact_ref) is None:
            raise ValueError("La invitación no está vinculada a un contacto local.")
        result = client.reissue_invitation(invitation_id)
        local = replace_invitation(
            invitation_id,
            str(result["invitation_id"]),
            contact_ref=contact_ref,
        )
    except ValueError as exc:
        return HTTPStatus.CONFLICT, error_payload("local_mapping_error", str(exc))
    except HostedRegistrationError as exc:
        return HTTPStatus(exc.status), error_payload(exc.code, str(exc))
    return HTTPStatus.CREATED, {
        **result,
        "contact_ref": local["contact_ref"],
        "display_name": local["display_name"],
        "whatsapp_phone": local["whatsapp_phone"],
    }


def update_hosted_contact_name_payload(
    contact_ref: str,
    payload: dict[str, Any],
) -> tuple[HTTPStatus, dict[str, Any]]:
    if "display_name" not in payload:
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            "Incluye el nombre o una referencia vacía para retirarlo.",
        )
    try:
        local = update_registration_contact_name(
            contact_ref,
            str(payload.get("display_name") or ""),
        )
    except ValueError as exc:
        message = str(exc)
        status = HTTPStatus.NOT_FOUND if "not available" in message else HTTPStatus.BAD_REQUEST
        return status, error_payload(
            "not_found" if status == HTTPStatus.NOT_FOUND else "bad_request",
            message,
        )
    return HTTPStatus.OK, {
        "status": "updated",
        "contact_ref": local["contact_ref"],
        "display_name": local["display_name"],
    }


def hosted_invitation_action_path(path: str, action: str) -> str | None:
    prefix = "/api/v1/hosted-invitations/"
    suffix = f"/{action}"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    invitation_id = path[len(prefix) : -len(suffix)]
    return invitation_id or None


def hosted_contact_action_path(path: str, action: str) -> str | None:
    prefix = "/api/v1/hosted-invitations/contacts/"
    suffix = f"/{action}"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    contact_ref = path[len(prefix) : -len(suffix)]
    return contact_ref or None


def _phone_hint(phone: str) -> str:
    digits = "".join(character for character in phone if character.isdigit())
    return f"***{digits[-3:]}"


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
