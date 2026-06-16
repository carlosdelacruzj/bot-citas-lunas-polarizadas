from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from appointment_bot.browser.session import BLOCKED_RESOURCE_TYPES
from tests.helpers import make_settings


class BrowserSessionTests(unittest.TestCase):
    def test_images_are_not_blocked_and_screenshot_scale_defaults_to_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))

        self.assertNotIn("image", BLOCKED_RESOURCE_TYPES)
        self.assertEqual(settings.screenshot_device_scale_factor, 2)


if __name__ == "__main__":
    unittest.main()
