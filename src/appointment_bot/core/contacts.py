from __future__ import annotations

CONTACT_SOURCES = ("tiktok", "facebook", "whatsapp")


class ContactValidationError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def normalize_contact_name(value: str | None) -> str | None:
    return _normalize_optional_text(value)


def normalize_contact_source(value: str | None, *, required: bool = False) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        if required:
            raise ContactValidationError("contact_source", "La fuente de contacto es obligatoria.")
        return None
    normalized = normalized.lower()
    if normalized not in CONTACT_SOURCES:
        allowed = ", ".join(CONTACT_SOURCES)
        raise ContactValidationError(
            "contact_source",
            f"La fuente de contacto debe ser una de: {allowed}.",
        )
    return normalized


def normalize_contact_whatsapp(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    if normalized.startswith("@") or any(character.isalpha() for character in normalized):
        raise ContactValidationError(
            "contact_whatsapp",
            "Ingresa un numero de WhatsApp, no un nombre de usuario.",
        )
    allowed = set("+0123456789 -()")
    if any(character not in allowed for character in normalized):
        raise ContactValidationError(
            "contact_whatsapp",
            "El numero de WhatsApp contiene caracteres no permitidos.",
        )
    digits = "".join(character for character in normalized if character.isdigit())
    if not 8 <= len(digits) <= 15:
        raise ContactValidationError(
            "contact_whatsapp",
            "El WhatsApp debe tener entre 8 y 15 digitos.",
        )
    if normalized.startswith("+"):
        return f"+{digits}"
    if len(digits) == 9 and digits.startswith("9"):
        return f"+51{digits}"
    if 10 <= len(digits) <= 15:
        return f"+{digits}"
    raise ContactValidationError(
        "contact_whatsapp",
        "Ingresa un celular peruano de 9 digitos o incluye el codigo de pais.",
    )


def normalize_contact_whatsapp_username(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    if not normalized.startswith("@") or len(normalized) < 2:
        raise ContactValidationError(
            "contact_whatsapp_username",
            "El usuario de WhatsApp debe comenzar con @.",
        )
    if len(normalized) > 100 or any(character.isspace() for character in normalized):
        raise ContactValidationError(
            "contact_whatsapp_username",
            "El usuario de WhatsApp no puede contener espacios y debe tener hasta 100 caracteres.",
        )
    return normalized


def resolve_whatsapp_recipient(
    phone: str | None,
    username: str | None,
) -> tuple[str | None, str | None]:
    normalized_phone = normalize_contact_whatsapp(phone)
    normalized_username = normalize_contact_whatsapp_username(username)
    if normalized_phone is not None:
        return normalized_phone, None
    if normalized_username is not None:
        return None, normalized_username
    raise ContactValidationError(
        "contact_whatsapp",
        "Registra un numero o un usuario de WhatsApp.",
    )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


__all__ = [
    "CONTACT_SOURCES",
    "ContactValidationError",
    "normalize_contact_name",
    "normalize_contact_source",
    "normalize_contact_whatsapp",
    "normalize_contact_whatsapp_username",
    "resolve_whatsapp_recipient",
]
