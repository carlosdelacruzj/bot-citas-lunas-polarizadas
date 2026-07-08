from __future__ import annotations

import base64
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from appointment_bot.flows.reservation_captcha_capture import save_reservation_captcha_image
from appointment_bot.flows.reservation_captcha_refresh import (
    ensure_reservation_captcha_loaded,
)
from appointment_bot.flows.reservation_submit import (
    solve_reservation_captcha_and_click_reserve,
)
from tests.helpers import make_settings

_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)


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

    def evaluate_all(self, *args):
        self.reloaded = True
        return True


class _CaptchaPanel:
    def __init__(self):
        self.page = _CaptchaPage()
        self.images = _CaptchaImages()

    def locator(self, selector):
        return self.images


class _IsolatedCaptchaMedia:
    def __init__(self):
        self.screenshot_paths: list[str] = []

    def scroll_into_view_if_needed(self, **kwargs):
        return None

    def screenshot(self, *, path, **kwargs):
        self.screenshot_paths.append(path)
        Path(path).write_bytes(_ONE_PIXEL_PNG)

    def bounding_box(self):
        return {"width": 210, "height": 90}

    def evaluate(self, script):
        data_uri = (
            "data:image/jpeg;base64,"
            + base64.b64encode(_ONE_PIXEL_PNG).decode("ascii")
        )
        if "return element.currentSrc || element.getAttribute" in script:
            return data_uri
        return {
            "devicePixelRatio": 2,
            "tagName": "IMG",
            "cssWidth": 210,
            "cssHeight": 90,
            "naturalWidth": 210,
            "naturalHeight": 90,
            "currentSrc": data_uri,
        }


class _IsolatedCaptchaMediaGroup:
    def __init__(self, media: _IsolatedCaptchaMedia):
        self.media = media

    def evaluate_all(self, *args):
        return 0

    def nth(self, index):
        return self.media


class _IsolatedCaptchaPanel:
    def __init__(self, page):
        self.page = page
        self.media = _IsolatedCaptchaMedia()
        self.screenshot_called = False

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def evaluate(self, script):
        return None

    def locator(self, selector):
        return _IsolatedCaptchaMediaGroup(self.media)

    def screenshot(self, **kwargs):
        self.screenshot_called = True


class _IsolatedCaptchaPage:
    def __init__(self):
        self.panel = _IsolatedCaptchaPanel(self)

    def locator(self, selector):
        return self.panel

    def evaluate(self, script):
        return None


class ReservationCaptchaTests(unittest.TestCase):
    def test_captcha_image_is_preserved_after_solving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            captcha = root / "captcha.png"
            captcha.write_bytes(b"image")
            events: list[str] = []
            captcha_audit: dict[str, object] = {}

            with (
                patch(
                    "appointment_bot.flows.reservation_submit.save_reservation_captcha_image",
                    return_value=captcha,
                ),
                patch(
                    "appointment_bot.flows.reservation_submit.solve_normal_captcha",
                    return_value="1234",
                ) as solve_captcha,
                patch(
                    "appointment_bot.flows.reservation_submit.validate_selected_appointment",
                ),
                patch(
                    "appointment_bot.flows.reservation_submit.save_screenshot",
                    return_value=None,
                ),
            ):
                solve_reservation_captcha_and_click_reserve(
                    _Page(),
                    settings,
                    can_submit=lambda: True,
                    on_submission_intent=lambda: events.append("intent"),
                    on_submission_started=lambda: events.append("started"),
                    captcha_audit=captcha_audit,
                )

            self.assertTrue(captcha.exists())
            solve_captcha.assert_called_once_with(captcha, settings)
            self.assertEqual(captcha_audit["captcha_image_path"], str(captcha))
            self.assertEqual(captcha_audit["captcha_screenshot_image_path"], str(captcha))
            self.assertEqual(captcha_audit["captcha_sent_source"], "screenshot")
            self.assertEqual(events, ["intent", "started"])

    def test_original_html_captcha_is_sent_to_solver_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            captcha = root / "captcha-screenshot.png"
            original = root / "captcha-original.png"
            captcha.write_bytes(b"screenshot")
            original.write_bytes(b"original")
            captcha_audit: dict[str, object] = {}

            def save_captcha(*args, **kwargs):
                audit = kwargs["captcha_audit"]
                audit["captcha_original_html_path"] = str(original)
                return captcha

            with (
                patch(
                    "appointment_bot.flows.reservation_submit.save_reservation_captcha_image",
                    side_effect=save_captcha,
                ),
                patch(
                    "appointment_bot.flows.reservation_submit.solve_normal_captcha",
                    return_value="1234",
                ) as solve_captcha,
                patch(
                    "appointment_bot.flows.reservation_submit.validate_selected_appointment",
                ),
                patch(
                    "appointment_bot.flows.reservation_submit.save_screenshot",
                    return_value=None,
                ),
            ):
                solve_reservation_captcha_and_click_reserve(
                    _Page(),
                    settings,
                    can_submit=lambda: True,
                    captcha_audit=captcha_audit,
                )

            solve_captcha.assert_called_once_with(original, settings)
            self.assertEqual(captcha_audit["captcha_image_path"], str(original))
            self.assertEqual(captcha_audit["captcha_screenshot_image_path"], str(captcha))
            self.assertEqual(captcha_audit["captcha_sent_source"], "original_html")

    def test_reservation_captcha_capture_uses_isolated_media_not_panel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = make_settings(root)
            page = _IsolatedCaptchaPage()
            captcha_audit: dict[str, object] = {}

            with patch(
                "appointment_bot.flows.reservation_captcha_capture.ensure_reservation_captcha_loaded",
                return_value=True,
            ):
                path = save_reservation_captcha_image(
                    page,
                    settings,
                    "captcha-test",
                    captcha_audit=captcha_audit,
                )

            self.assertFalse(path.exists())
            self.assertEqual(path.parent.name, "captchas")
            self.assertEqual(
                path.parent.parent.name,
                datetime.now(ZoneInfo("America/Lima")).strftime("%d-%m-%Y"),
            )
            self.assertEqual(page.panel.media.screenshot_paths, [])
            self.assertFalse(page.panel.screenshot_called)
            self.assertEqual(captcha_audit["captcha_element_css_width"], 210)
            self.assertEqual(captcha_audit["captcha_element_css_height"], 90)
            self.assertEqual(captcha_audit["captcha_device_scale_factor"], 2)
            self.assertEqual(captcha_audit["captcha_natural_width"], 210)
            self.assertEqual(captcha_audit["captcha_natural_height"], 90)
            original_path = Path(str(captcha_audit["captcha_original_html_path"]))
            self.assertTrue(original_path.exists())
            self.assertEqual(original_path.read_bytes(), _ONE_PIXEL_PNG)
            self.assertEqual(captcha_audit["captcha_original_html_source"], "data_uri")
            self.assertEqual(captcha_audit["captcha_original_html_mime"], "image/jpeg")
            self.assertEqual(captcha_audit["captcha_original_html_detected_format"], "png")
            self.assertEqual(captcha_audit["captcha_original_html_bytes"], len(_ONE_PIXEL_PNG))
            self.assertEqual(captcha_audit["captcha_original_html_width"], 1)
            self.assertEqual(captcha_audit["captcha_original_html_height"], 1)

    def test_broken_captcha_image_is_reloaded_before_capture(self) -> None:
        panel = _CaptchaPanel()
        with patch(
            "appointment_bot.flows.reservation_captcha_refresh._wait_for_panel_captcha",
            side_effect=[False, True],
        ):
            loaded = ensure_reservation_captcha_loaded(panel, timeout=1)

        self.assertTrue(loaded)
        self.assertTrue(panel.images.reloaded)


if __name__ == "__main__":
    unittest.main()
