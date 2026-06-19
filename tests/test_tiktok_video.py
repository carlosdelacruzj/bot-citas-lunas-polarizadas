from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from appointment_bot.services.tiktok_video import (
    DEFAULT_MAX_SECONDS,
    _export_duration,
    latest_diagnostic_video,
)


class TikTokVideoTests(unittest.TestCase):
    def test_latest_diagnostic_video_uses_newest_matching_webm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older = root / "appointment-bot-diagnostic-20260616-010000.webm"
            newer = root / "appointment-bot-diagnostic-20260616-020000.webm"
            ignored = root / "other.webm"
            older.write_bytes(b"old")
            time.sleep(0.01)
            newer.write_bytes(b"new")
            time.sleep(0.01)
            ignored.write_bytes(b"ignored")

            self.assertEqual(latest_diagnostic_video(root), newer)

    def test_export_duration_loops_short_video_and_caps_long_video(self) -> None:
        self.assertEqual(_export_duration(10, 24), 24)
        self.assertEqual(_export_duration(27, 24), 27)
        self.assertEqual(_export_duration(80, 24), DEFAULT_MAX_SECONDS)


if __name__ == "__main__":
    unittest.main()
