from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.core.models import RunReport
from appointment_bot.core.run_reports import reservation_confirmed

logger = logging.getLogger(__name__)
FFMPEG_TIMEOUT_SECONDS = 120


@dataclass
class ClientSessionVideoRecorder:
    evidence_settings: EvidenceSettings
    order_id: str
    client_name: str
    started_at: datetime
    temp_directory: TemporaryDirectory[str]
    source_path: Path | None = None

    @classmethod
    def create(
        cls,
        *,
        order_id: str | None,
        client_name: str | None,
        started_at: datetime,
        evidence_settings: EvidenceSettings,
    ) -> ClientSessionVideoRecorder | None:
        if not evidence_settings.record_client_sessions or order_id is None:
            return None
        return cls(
            order_id=order_id or "observer",
            client_name=client_name or order_id or "observer",
            started_at=started_at,
            temp_directory=tempfile.TemporaryDirectory(prefix="appointment-bot-client-video-"),
            evidence_settings=evidence_settings,
        )

    @property
    def record_video_dir(self) -> Path:
        return Path(self.temp_directory.name)

    def capture_source_path(self, path: Path | None) -> None:
        self.source_path = path

    def finalize(self, report: RunReport) -> Path | None:
        try:
            if self.source_path is None or not self.source_path.exists():
                return None

            if _retain_diagnostic_video(report):
                diagnostic_dir = self.evidence_settings.client_videos_dir / "diagnostics"
                diagnostic_dir.mkdir(parents=True, exist_ok=True)
                target_path = self._target_path(
                    f"-{report.run_id or 'session'}-{report.status}-diagnostic.webm",
                    directory=diagnostic_dir,
                )
                self.source_path.replace(target_path)
                target_path.with_suffix(".json").write_text(
                    json.dumps(
                        {
                            "run_id": report.run_id,
                            "status": report.status,
                            "message": report.message,
                            "screenshot_path": report.screenshot_path,
                            "reservation_attempted": report.reservation_attempted,
                            "video_path": str(target_path),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return target_path

            if not reservation_confirmed(report):
                _remove_file(self.source_path)
                return None

            self.evidence_settings.client_videos_dir.mkdir(parents=True, exist_ok=True)
            target_path = self._target_path(
                ".mp4" if self.evidence_settings.record_client_video_final_mp4 else ".webm"
            )
            if not self.evidence_settings.record_client_video_final_mp4:
                self.source_path.replace(target_path)
                return target_path

            exported_path = _export_mp4(
                self.source_path, target_path, evidence_settings=self.evidence_settings
            )
            if exported_path is None:
                fallback_path = self._target_path(".webm")
                self.source_path.replace(fallback_path)
                return fallback_path
            _remove_file(self.source_path)
            return exported_path
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        self.temp_directory.cleanup()

    def _target_path(self, suffix: str, *, directory: Path | None = None) -> Path:
        stamp = self.started_at.strftime("%Y%m%d-%H%M%S")
        client_name = _safe_filename(self.client_name)
        target_dir = directory or self.evidence_settings.client_videos_dir
        path = target_dir / f"{stamp}-{client_name}{suffix}"
        if not path.exists():
            return path
        return target_dir / f"{stamp}-{client_name}-{self.order_id}{suffix}"


def _retain_diagnostic_video(report: RunReport) -> bool:
    details = report.details or {}
    return bool(
        not reservation_confirmed(report)
        and (
            report.exit_code
            or report.status in {"error", "unknown", "reservation_unconfirmed"}
            or report.reservation_attempted
            or details.get("worker_pause_required")
            or details.get("canonical_slot_capture")
            or details.get("reservation_button_interaction")
            or details.get("error_type")
            or details.get("portal_contract_change")
        )
    )


def _export_mp4(
    source_path: Path, target_path: Path, *, evidence_settings: EvidenceSettings
) -> Path | None:
    try:
        ffmpeg = _find_executable("ffmpeg")
    except FileNotFoundError as exc:
        logger.warning("Could not export client session video: %s", exc)
        return None

    if evidence_settings.client_video_width < evidence_settings.client_video_height:
        video_filter = "crop=900:1600:90:0,scale=1080:1920,fps=30,format=yuv420p"
    else:
        video_filter = "fps=30,format=yuv420p"
    command = [
        str(ffmpeg),
        "-y",
        "-i",
        str(source_path),
        "-vf",
        video_filter,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-movflags",
        "+faststart",
        str(target_path),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("Could not export client session video: %s", exc)
        return None
    return target_path


def _safe_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", ascii_value).strip("-_")
    return cleaned or "cliente"


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove client session video %s: %s", path, exc)


def _find_executable(name: str) -> Path:
    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(f"Required executable was not found: {name}")
    return Path(executable)
