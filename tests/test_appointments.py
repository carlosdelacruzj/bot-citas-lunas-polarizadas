from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from appointment_bot.flows.appointments import (
    _is_real_appointment_option,
    ensure_reservation_captcha_loaded,
    solve_reservation_captcha_and_click_reserve,
)
from appointment_bot.flows.stages import appointment_stage_result
from tests.helpers import make_settings


class _Locator:
    @property
    def first(self):
        return self

    def wait_for(self, **kwargs):
        return None

    def fill(self, value, **kwargs):
        return None

    def scroll_into_view_if_needed(self, **kwargs):
        return None

    def click(self, **kwargs):
        return None


class _Page:
    url = "https://example.invalid/result"

    def locator(self, selector):
        return _Locator()

    def wait_for_load_state(self, *args, **kwargs):
        return None


class _CaptchaPage:
    def __init__(self):
        self.waits = 0

    def wait_for_timeout(self, milliseconds):
        self.waits += 1


class _CaptchaImages:
    def __init__(self):
        self.reloaded = False

    def evaluate_all(self, script):
        self.reloaded = True
        return True


class _CaptchaPanel:
    def __init__(self):
        self.page = _CaptchaPage()
        self.images = _CaptchaImages()

    def locator(self, selector):
        return self.images


class AppointmentFlowTests(unittest.TestCase):
    def test_missing_stage_is_unknown(self) -> None:
        result = appointment_stage_result([])
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "unknown")

    def test_disabled_or_empty_options_are_not_available(self) -> None:
        self.assertFalse(
            _is_real_appointment_option(
                {"text": "10:00", "value": "10", "disabled": True, "hidden": False}
            )
        )
        self.assertFalse(
            _is_real_appointment_option(
                {"text": "Información", "value": "", "disabled": False, "hidden": False}
            )
        )

    def test_temporary_captcha_is_deleted_after_solving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            captcha = root / "captcha.png"
            captcha.write_bytes(b"image")
            events: list[str] = []

            with (
                patch(
                    "appointment_bot.flows.appointments._save_reservation_panel_image",
                    return_value=captcha,
                ),
                patch(
                    "appointment_bot.flows.appointments.solve_normal_captcha",
                    return_value="1234",
                ),
                patch(
                    "appointment_bot.flows.appointments.validate_selected_appointment",
                ),
            ):
                solve_reservation_captcha_and_click_reserve(
                    _Page(),
                    settings,
                    can_submit=lambda: True,
                    on_submission_intent=lambda: events.append("intent"),
                    on_submission_started=lambda: events.append("started"),
                )

            self.assertFalse(captcha.exists())
            self.assertEqual(events, ["intent", "started"])

    def test_broken_captcha_image_is_reloaded_before_capture(self) -> None:
        panel = _CaptchaPanel()
        with patch(
            "appointment_bot.flows.appointments._wait_for_panel_captcha",
            side_effect=[False, True],
        ):
            loaded = ensure_reservation_captcha_loaded(panel, timeout=1)

        self.assertTrue(loaded)
        self.assertTrue(panel.images.reloaded)


if __name__ == "__main__":
    unittest.main()
