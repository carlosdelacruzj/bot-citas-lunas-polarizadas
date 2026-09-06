from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.reservation_engine.appointment_contracts import (
    PortalContractChanged,
)
from appointment_bot.reservation_engine.reservation_controls import (
    RESERVATION_HONEYPOT_SELECTOR,
    RESERVATION_MATH_CAPTCHA_SELECTOR,
)

MATH_CAPTCHA_PATTERN = re.compile(r"^\s*(\d{1,3})\s*\+\s*(\d{1,3})\s*=\s*\?\s*$")
MAX_MATH_CAPTCHA_ANSWER = 999


@dataclass(frozen=True)
class MathCaptchaChallenge:
    answer: str
    signature: str


def has_reservation_math_captcha(scope) -> bool:
    try:
        return scope.locator(RESERVATION_MATH_CAPTCHA_SELECTOR).count() > 0
    except (AttributeError, PlaywrightError):
        return False


def read_reservation_math_captcha(
    scope,
    *,
    selector: str = RESERVATION_MATH_CAPTCHA_SELECTOR,
) -> MathCaptchaChallenge | None:
    try:
        locator = scope.locator(selector)
        count = locator.count()
    except AttributeError:
        return None
    if count == 0:
        return None
    if count != 1:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el CAPTCHA matematico no es unico."
        )

    label = locator.first
    bounds = label.bounding_box()
    if bounds is None or bounds["width"] < 40 or bounds["height"] < 20:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el CAPTCHA matematico no esta visible."
        )

    expression = label.inner_text().strip()
    match = MATH_CAPTCHA_PATTERN.fullmatch(expression)
    if match is None:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el CAPTCHA matematico tiene un formato "
            "no reconocido."
        )

    left = int(match.group(1))
    right = int(match.group(2))
    answer = left + right
    if answer > MAX_MATH_CAPTCHA_ANSWER:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: la operacion CAPTCHA excede el formato "
            "conocido."
        )

    normalized = f"{left}+{right}=?"
    signature = hashlib.sha256(normalized.encode("ascii")).hexdigest()
    return MathCaptchaChallenge(answer=str(answer), signature=signature)


def ensure_reservation_honeypot_empty(page: Page) -> None:
    try:
        honeypot = page.locator(RESERVATION_HONEYPOT_SELECTOR)
        count = honeypot.count()
    except AttributeError as exc:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: no se pudo inspeccionar el honeypot."
        ) from exc
    if count == 0:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: falta el honeypot esperado."
        )
    if count != 1:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el honeypot no es unico."
        )
    if honeypot.first.input_value() != "":
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el honeypot contiene un valor inesperado."
        )


def validate_reservation_math_captcha(
    page: Page,
    *,
    expected_signature: str,
    selector: str = RESERVATION_MATH_CAPTCHA_SELECTOR,
) -> MathCaptchaChallenge:
    challenge = read_reservation_math_captcha(page, selector=selector)
    if challenge is None:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el CAPTCHA desaparecio antes del envio."
        )
    if challenge.signature != expected_signature:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el CAPTCHA cambio antes del envio."
        )
    ensure_reservation_honeypot_empty(page)
    return challenge
