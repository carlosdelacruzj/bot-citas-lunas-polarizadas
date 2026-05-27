import logging
from pathlib import Path

from twocaptcha import TwoCaptcha

from appointment_bot.config import Settings

logger = logging.getLogger(__name__)


def solve_normal_captcha(image_path: Path, settings: Settings) -> str:
    if not settings.captcha_api_key:
        raise ValueError("APIKEY_2CAPTCHA is required to solve the reservation captcha.")

    logger.info("Sending reservation captcha to 2captcha: %s", image_path)
    result = TwoCaptcha(settings.captcha_api_key).normal(str(image_path))
    solution = str(result.get("code") or "").strip()
    if not solution:
        raise RuntimeError(f"2captcha returned an empty captcha solution: {result}")

    logger.info("2captcha solved reservation captcha")
    return solution
