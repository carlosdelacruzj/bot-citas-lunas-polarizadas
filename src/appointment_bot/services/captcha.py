import logging
from pathlib import Path

from twocaptcha import TwoCaptcha

from appointment_bot.configuration.captcha import CaptchaSettings
from appointment_bot.configuration.reservation import ReservationSettings

logger = logging.getLogger(__name__)
CAPTCHA_POLLING_INTERVAL_SECONDS = 5


def solve_normal_captcha(
    image_path: Path,
    *,
    reservation_settings: ReservationSettings,
    captcha_settings: CaptchaSettings,
) -> str:
    if not captcha_settings.captcha_api_key:
        raise ValueError("APIKEY_2CAPTCHA is required to solve the reservation captcha.")

    logger.info("Sending reservation captcha to 2captcha: %s", image_path)
    solver = TwoCaptcha(
        captcha_settings.captcha_api_key,
        defaultTimeout=reservation_settings.reservation_timeout_seconds,
        pollingInterval=CAPTCHA_POLLING_INTERVAL_SECONDS,
    )
    result = solver.normal(
        str(image_path), timeout=reservation_settings.reservation_timeout_seconds
    )
    solution = str(result.get("code") or "").strip()
    if not solution:
        raise RuntimeError(f"2captcha returned an empty captcha solution: {result}")

    logger.info("2captcha solved reservation captcha")
    return solution
