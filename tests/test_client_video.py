from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from appointment_bot.domain import RunReport
from appointment_bot.services.client_video import ClientSessionVideoRecorder, _safe_filename
from tests.helpers import make_settings


class ClientSessionVideoTests(unittest.TestCase):
    def test_recorder_is_disabled_without_flag_or_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))

        self.assertIsNone(
            ClientSessionVideoRecorder.create(
                settings,
                order_id="client-1",
                client_name="Client One",
                started_at=datetime(2026, 6, 16, 18, 0, 0),
            )
        )
        enabled = replace(settings, record_client_sessions=True)
        self.assertIsNone(
            ClientSessionVideoRecorder.create(
                enabled,
                order_id=None,
                client_name=None,
                started_at=datetime(2026, 6, 16, 18, 0, 0),
            )
        )

    def test_unconfirmed_result_removes_temporary_video(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = replace(make_settings(root), record_client_sessions=True)
            source = root / "temp.webm"
            source.write_bytes(b"video")
            recorder = ClientSessionVideoRecorder.create(
                settings,
                order_id="client-1",
                client_name="Client One",
                started_at=datetime(2026, 6, 16, 18, 0, 0),
            )
            assert recorder is not None
            recorder.capture_source_path(source)

            result = recorder.finalize(
                RunReport(status="unavailable", message="Sin cupos", exit_code=0)
            )

        self.assertIsNone(result)
        self.assertFalse(source.exists())

    def test_registered_result_keeps_webm_when_mp4_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = replace(
                make_settings(root),
                record_client_sessions=True,
                record_client_video_final_mp4=False,
            )
            source = root / "temp.webm"
            source.write_bytes(b"video")
            recorder = ClientSessionVideoRecorder.create(
                settings,
                order_id="client-1",
                client_name="Maria Perez",
                started_at=datetime(2026, 6, 16, 18, 0, 0),
            )
            assert recorder is not None
            recorder.capture_source_path(source)

            result = recorder.finalize(
                RunReport(status="registered", message="Reservado", exit_code=0)
            )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.name, "20260616-180000-Maria-Perez.webm")
            self.assertTrue(result.exists())
            self.assertFalse(source.exists())

    def test_registered_result_exports_mp4_and_removes_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = replace(make_settings(root), record_client_sessions=True)
            source = root / "temp.webm"
            source.write_bytes(b"video")
            recorder = ClientSessionVideoRecorder.create(
                settings,
                order_id="client-1",
                client_name="Maria Perez",
                started_at=datetime(2026, 6, 16, 18, 0, 0),
            )
            assert recorder is not None
            recorder.capture_source_path(source)

            def fake_export(_settings, _source_path, target_path):
                target_path.write_bytes(b"mp4")
                return target_path

            with patch("appointment_bot.services.client_video._export_mp4", fake_export):
                result = recorder.finalize(
                    RunReport(status="registered", message="Reservado", exit_code=0)
                )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.name, "20260616-180000-Maria-Perez.mp4")
            self.assertTrue(result.exists())
            self.assertFalse(source.exists())

    def test_safe_filename_removes_risky_characters(self) -> None:
        self.assertEqual(_safe_filename("Maria / Perez: DNI 123"), "Maria-Perez-DNI-123")
        self.assertEqual(_safe_filename("***"), "cliente")


if __name__ == "__main__":
    unittest.main()
