from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

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


def read_reservation_math_captcha(scope) -> MathCaptchaChallenge | None:
    try:
        locator = scope.locator(RESERVATION_MATH_CAPTCHA_SELECTOR)
        count = locator.count()
    except AttributeError:
        return None
    if count == 0:
        return None
    if count != 1:
        raise RuntimeError("The reservation math captcha is ambiguous in the portal DOM.")

    label = locator.first
    bounds = label.bounding_box()
    if bounds is None or bounds["width"] < 40 or bounds["height"] < 20:
        raise RuntimeError("The reservation math captcha is not visibly rendered.")

    expression = label.inner_text().strip()
    match = MATH_CAPTCHA_PATTERN.fullmatch(expression)
    if match is None:
        raise RuntimeError("The reservation math captcha has an unsupported format.")

    left = int(match.group(1))
    right = int(match.group(2))
    answer = left + right
    if answer > MAX_MATH_CAPTCHA_ANSWER:
        raise RuntimeError("The reservation math captcha answer exceeds the portal field.")

    normalized = f"{left}+{right}=?"
    signature = hashlib.sha256(normalized.encode("ascii")).hexdigest()
    return MathCaptchaChallenge(answer=str(answer), signature=signature)


def ensure_reservation_honeypot_empty(page: Page) -> None:
    try:
        honeypot = page.locator(RESERVATION_HONEYPOT_SELECTOR)
        count = honeypot.count()
    except AttributeError:
        return
    if count == 0:
        return
    if count != 1:
        raise RuntimeError("The reservation honeypot is ambiguous in the portal DOM.")
    if honeypot.first.input_value() != "":
        raise RuntimeError("The reservation honeypot is not empty; submit was blocked.")


def validate_reservation_math_captcha(
    page: Page,
    *,
    expected_signature: str,
) -> MathCaptchaChallenge:
    challenge = read_reservation_math_captcha(page)
    if challenge is None:
        raise RuntimeError("The reservation math captcha disappeared before submit.")
    if challenge.signature != expected_signature:
        raise RuntimeError("The reservation math captcha changed before submit.")
    ensure_reservation_honeypot_empty(page)
    return challenge
