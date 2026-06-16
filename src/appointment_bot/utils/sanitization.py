import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def sanitize_url(url: str) -> str:
    parsed = urlsplit(url)
    redacted_query = urlencode([(key, "***") for key, _value in parse_qsl(parsed.query)])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, redacted_query, ""))
