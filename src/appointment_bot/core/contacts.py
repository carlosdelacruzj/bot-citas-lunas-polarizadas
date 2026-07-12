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
    digits = "".join(character for character in normalized if character.isdigit())
    if not digits:
        raise ContactValidationError(
            "contact_whatsapp",
            "El WhatsApp debe contener al menos un digito.",
        )
    return f"+{digits}" if normalized.startswith("+") else digits


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
]
