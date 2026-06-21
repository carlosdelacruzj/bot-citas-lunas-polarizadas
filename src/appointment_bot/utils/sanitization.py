import re

SENSITIVE_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    re.compile(r"\b\d{8,12}\b"),
    re.compile(r"(?i)\b(?:bearer|token|password|secret)\s*[:=]\s*\S+"),
)


def sanitize_text(text: str) -> str:
    sanitized = text
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("***", sanitized)
    return sanitized


def normalize_option(value: str) -> str:
    return " ".join(value.strip().lower().split())


def public_filename(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).replace("\\", "/").rsplit("/", maxsplit=1)[-1]
