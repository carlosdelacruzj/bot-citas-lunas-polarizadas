import logging
from pathlib import Path

from twocaptcha import TwoCaptcha

from appointment_bot.config import Settings

logger = logging.getLogger(__name__)
CAPTCHA_POLLING_INTERVAL_SECONDS = 5


def solve_normal_captcha(image_path: Path, settings: Settings) -> str:
    if not settings.captcha_api_key:
        raise ValueError("APIKEY_2CAPTCHA is required to solve the reservation captcha.")

    logger.info("Sending reservation captcha to 2captcha: %s", image_path)
    solver = TwoCaptcha(
        settings.captcha_api_key,
        defaultTimeout=settings.reservation_timeout_seconds,
        pollingInterval=CAPTCHA_POLLING_INTERVAL_SECONDS,
    )
    result = solver.normal(
        str(image_path),
        timeout=settings.reservation_timeout_seconds,
    )
    solution = str(result.get("code") or "").strip()
    if not solution:
        raise RuntimeError(f"2captcha returned an empty captcha solution: {result}")

    logger.info("2captcha solved reservation captcha")
    return solution
