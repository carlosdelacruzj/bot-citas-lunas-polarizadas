from __future__ import annotations

import unittest

from appointment_bot.utils.screenshots import mask_sensitive_page


class _Page:
    def __init__(self):
        self.scripts: list[str] = []

    def evaluate(self, script):
        self.scripts.append(script)


class ScreenshotPrivacyTests(unittest.TestCase):
    def test_mask_preserves_action_buttons_and_masks_captcha_controls(self) -> None:
        page = _Page()

        with mask_sensitive_page(page):
            pass

        masking_script = page.scripts[0]
        self.assertIn('"submit"', masking_script)
        self.assertIn('"image"', masking_script)
        self.assertIn('"txtimg"', masking_script)
        self.assertIn("isSensitive && canContainSecret", masking_script)


if __name__ == "__main__":
    unittest.main()
