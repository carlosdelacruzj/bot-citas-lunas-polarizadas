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
        self.assertEqual(settings.client_video_width, 1920)
        self.assertEqual(settings.client_video_height, 1080)
        self.assertFalse(settings.record_client_sessions)
        self.assertTrue(settings.record_client_video_final_mp4)
        self.assertEqual(settings.client_videos_dir.name, "reservations")


if __name__ == "__main__":
    unittest.main()
