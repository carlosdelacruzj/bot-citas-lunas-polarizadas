from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from appointment_bot.core.models import RunDetail, RunReport
from appointment_bot.reports.evidence import (
    append_evidence_rows,
    detect_defense_signal,
    evidence_row_from_report,
    export_evidence_summary,
    read_evidence_rows,
)


class EvidenceSummaryTests(unittest.TestCase):
    def test_registered_report_creates_compact_row(self) -> None:
        row = evidence_row_from_report(
            RunReport(
                status="registered",
                message="La reserva fue confirmada",
                exit_code=0,
                run_id="run-1",
                order_id="order-1",
                finished_at="2026-07-04T15:10:00+00:00",
                duration_seconds=42.3,
                reservation_attempted=True,
                reservation_confirmed=True,
                details={
                    "sede": "LIMA-LA VICTORIA",
                    "fecha": "14/07/2026",
                    "hora": "11:00",
                    "detection_origin": "normal",
                    "submission_outcome": "confirmed",
                    "confirmation_source": "portal_success_text",
                    "reservation_timing": {
                        "selection_seconds": 0.8,
                        "captcha_solver_seconds": 33.2,
                    },
                    "password": "secret",
                },
                screenshot_path="screenshots/result.png",
                screenshot_paths=["screenshots/result.png", "screenshots/extra.png"],
            )
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["status"], "registered")
        self.assertEqual(row["detection_origin"], "normal")
        self.assertEqual(row["confirmation_source"], "portal_success_text")
        self.assertEqual(row["captcha_solver_seconds"], "33.200")
        self.assertNotIn("secret", str(row))

    def test_evidence_cases_exclude_date_only_partial_and_include_failures(self) -> None:
        cases = [
            RunReport(
                status="partial",
                message="Fecha visible sin hora",
                exit_code=0,
                run_id="run-partial",
                details={"fetch_probe": True, "fecha": "04/07/2026"},
            ),
            RunReport(
                status="error",
                message="El portal respondio captcha_invalid",
                exit_code=1,
                run_id="run-captcha",
                details={"submission_outcome": "captcha_invalid"},
            ),
            RunReport(
                status="error",
                message="HTTP 429 Too Many Requests",
                exit_code=1,
                run_id="run-defense",
            ),
        ]

        rows = [evidence_row_from_report(case) for case in cases]

        self.assertIsNone(rows[0])
        assert rows[1] is not None
        assert rows[2] is not None
        self.assertEqual(rows[1]["submission_outcome"], "captcha_invalid")
        self.assertEqual(rows[2]["defense_signal"], "http_429")

    def test_append_deduplicates_by_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.csv"
            row = {
                "run_id": "run-1",
                "finished_at_lima": "2026-07-04 10:00:00",
                "status": "registered",
            }

            append_evidence_rows(path, [row])
            append_evidence_rows(path, [row])

            rows = read_evidence_rows(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["run_id"], "run-1")

    def test_export_evidence_summary_writes_csv_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = RunDetail(
                run_id="run-1",
                order_id="order-1",
                status="registered",
                message="Reserva lista",
                exit_code=0,
                started_at="2026-07-04T14:00:00+00:00",
                finished_at="2026-07-04T14:01:00+00:00",
                duration_seconds=60,
                reservation_attempted=True,
                reservation_confirmed=True,
                screenshot_path="result.png",
                screenshot_count=1,
                created_at="2026-07-04T14:01:00+00:00",
                details={"fecha": "14/07/2026", "hora": "11:00"},
                screenshot_paths=["result.png"],
            )

            result = export_evidence_summary(
                [run],
                output_dir=root,
                days=7,
                now=datetime(2026, 7, 4, 15, tzinfo=UTC),
            )

            self.assertEqual(result.event_count, 1)
            self.assertTrue(result.csv_path.exists())
            self.assertTrue(result.markdown_path.exists())
            with result.csv_path.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[0]["run_id"], "run-1")
            summary = result.markdown_path.read_text(encoding="utf-8")
            self.assertIn("Generado: `2026-07-04 10:00:00 America/Lima`", summary)
            self.assertIn("Rango real de eventos indexados", summary)
            self.assertIn("Cobertura temporal verificable: 1/1", summary)
            self.assertIn("Es un snapshot generado", summary)
            self.assertIn("Reservas registradas: 1", summary)

    def test_defense_signal_detection(self) -> None:
        self.assertEqual(detect_defense_signal("HTTP 403 forbidden"), "http_403")
        self.assertEqual(detect_defense_signal("sin cupos"), "")


if __name__ == "__main__":
    unittest.main()
