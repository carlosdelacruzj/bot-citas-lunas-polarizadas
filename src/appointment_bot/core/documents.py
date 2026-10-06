from __future__ import annotations

DOCUMENT_TYPE_DNI = "dni"
DOCUMENT_TYPE_FOREIGN_RESIDENT_CARD = "foreign_resident_card"
DOCUMENT_TYPES = (DOCUMENT_TYPE_DNI, DOCUMENT_TYPE_FOREIGN_RESIDENT_CARD)

PORTAL_DOCUMENT_TYPE_VALUES = {
    DOCUMENT_TYPE_DNI: "1",
    DOCUMENT_TYPE_FOREIGN_RESIDENT_CARD: "2",
}


def normalize_document_type(value: str | None) -> str:
    normalized = (value or DOCUMENT_TYPE_DNI).strip().lower()
    aliases = {
        "ce": DOCUMENT_TYPE_FOREIGN_RESIDENT_CARD,
        "carnet_extranjeria": DOCUMENT_TYPE_FOREIGN_RESIDENT_CARD,
        "carnet_de_extranjeria": DOCUMENT_TYPE_FOREIGN_RESIDENT_CARD,
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in DOCUMENT_TYPES:
        raise ValueError("document_type must be dni or foreign_resident_card.")
    return normalized
