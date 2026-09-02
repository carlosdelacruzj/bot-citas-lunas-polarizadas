from __future__ import annotations

import random
import unicodedata

from appointment_bot.config import Settings


def portal_defense_signal(message: str) -> str | None:
    normalized = ascii_fold(message).casefold()
    signals = (
        ("http 429", "limite HTTP 429"),
        ("http error 429", "limite HTTP 429"),
        ("response status 429", "limite HTTP 429"),
        ("status 429", "limite HTTP 429"),
        ("too many requests", "limite de solicitudes"),
        ("http 403", "bloqueo HTTP 403"),
        ("http error 403", "bloqueo HTTP 403"),
        ("response status 403", "bloqueo HTTP 403"),
        ("status 403", "bloqueo HTTP 403"),
        ("forbidden", "bloqueo HTTP 403"),
        ("access denied", "acceso denegado"),
        ("captcha inesperado", "CAPTCHA inesperado"),
        ("sesion expirada", "sesion expirada"),
        ("session expired", "sesion expirada"),
        ("inicie sesion", "sesion cerrada por el portal"),
    )
    return next((label for text, label in signals if text in normalized), None)


def is_network_error(message: str) -> bool:
    normalized = ascii_fold(message).casefold()
    signals = (
        "net::err_",
        "connection reset",
        "connection refused",
        "connection aborted",
        "getaddrinfo failed",
        "name resolution",
        "temporary failure in name resolution",
        "urlopen error",
        "page.goto: timeout",
    )
    return any(signal in normalized for signal in signals)


def recovery_wait_seconds(settings: Settings) -> int:
    return random.randint(
        settings.recovery_backoff_min_seconds,
        settings.recovery_backoff_max_seconds,
    )


def ascii_fold(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
