from __future__ import annotations

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

from appointment_bot.config import Settings
from appointment_bot.domain import RunReport
from appointment_bot.reports.run_reporting import reservation_confirmed

logger = logging.getLogger(__name__)
FFMPEG_TIMEOUT_SECONDS = 120

CLIENT_SESSION_PRIVACY_SCRIPT = """
() => {
    const install = () => {
        if (!document.getElementById("appointment-bot-client-video-style")) {
            const style = document.createElement("style");
            style.id = "appointment-bot-client-video-style";
            style.textContent = `
                input:not([type="button"]):not([type="submit"]):not([type="reset"]):not([type="image"]),
                textarea {
                    color: transparent !important;
                    text-shadow: 0 0 0 #777 !important;
                    -webkit-text-security: disc !important;
                }
                .appointment-bot-visible-reservation input,
                .appointment-bot-visible-reservation textarea {
                    color: inherit !important;
                    text-shadow: none !important;
                    -webkit-text-security: none !important;
                }
            `;
            document.head.appendChild(style);
        }

        const captchaParts = ["captcha", "txtimg", "codigo"];
        const isCaptchaControl = element => {
            const key = [
                element.id, element.name, element.placeholder,
                element.getAttribute("aria-label")
            ].join(" ").toLowerCase();
            return captchaParts.some(part => key.includes(part));
        };
        const shouldShowReservationControl = element => {
            if (isCaptchaControl(element)) return false;
            let current = element;
            for (let depth = 0; current && depth < 5; depth += 1) {
                const text = current.innerText || "";
                if (/Reserva Cita( Peritaje)?/i.test(text) && text.length < 1200) {
                    current.classList.add("appointment-bot-visible-reservation");
                    return true;
                }
                current = current.parentElement;
            }
            return false;
        };
        Array.from(document.querySelectorAll("input, textarea")).forEach(element => {
            if (!shouldShowReservationControl(element)) return;
            element.style.setProperty("color", "inherit", "important");
            element.style.setProperty("text-shadow", "none", "important");
            element.style.setProperty("-webkit-text-security", "none", "important");
        });

        if (!document.getElementById("appointment-bot-video-header-mask")) {
            const mask = document.createElement("div");
            mask.id = "appointment-bot-video-header-mask";
            mask.textContent = "usuario oculto";
            mask.style.cssText = [
                "position:fixed",
                "top:54px",
                "left:0",
                "z-index:2147483647",
                "width:370px",
                "height:42px",
                "background:rgba(248,250,252,.98)",
                "color:#334155",
                "font:700 16px Arial,sans-serif",
                "display:flex",
                "align-items:center",
                "padding-left:16px",
                "pointer-events:none"
            ].join(";");
            document.body.appendChild(mask);
        }
    };
    if (!window.__appointmentBotClientVideoPrivacy) {
        window.__appointmentBotClientVideoPrivacy = true;
        window.setInterval(install, 250);
        document.addEventListener("DOMContentLoaded", install);
    }
    install();
}
"""


@dataclass
class ClientSessionVideoRecorder:
    settings: Settings
    order_id: str
    client_name: str
    started_at: datetime
    temp_directory: TemporaryDirectory[str]
    source_path: Path | None = None

    @classmethod
    def create(
        cls,
        settings: Settings,
        *,
        order_id: str | None,
        client_name: str | None,
        started_at: datetime,
    ) -> ClientSessionVideoRecorder | None:
        if not settings.record_client_sessions or order_id is None:
            return None
        return cls(
            settings=settings,
            order_id=order_id,
            client_name=client_name or order_id,
            started_at=started_at,
            temp_directory=tempfile.TemporaryDirectory(prefix="appointment-bot-client-video-"),
        )

    @property
    def init_script(self) -> str:
        return f"({CLIENT_SESSION_PRIVACY_SCRIPT})()"

    @property
    def record_video_dir(self) -> Path:
        return Path(self.temp_directory.name)

    def capture_source_path(self, path: Path | None) -> None:
        self.source_path = path

    def finalize(self, report: RunReport) -> Path | None:
        try:
            if self.source_path is None or not self.source_path.exists():
                return None

            if not reservation_confirmed(report):
                _remove_file(self.source_path)
                return None

            self.settings.client_videos_dir.mkdir(parents=True, exist_ok=True)
            target_path = self._target_path(
                ".mp4" if self.settings.record_client_video_final_mp4 else ".webm"
            )
            if not self.settings.record_client_video_final_mp4:
                self.source_path.replace(target_path)
                return target_path

            exported_path = _export_mp4(self.settings, self.source_path, target_path)
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

    def _target_path(self, suffix: str) -> Path:
        stamp = self.started_at.strftime("%Y%m%d-%H%M%S")
        client_name = _safe_filename(self.client_name)
        path = self.settings.client_videos_dir / f"{stamp}-{client_name}{suffix}"
        if not path.exists():
            return path
        return self.settings.client_videos_dir / f"{stamp}-{client_name}-{self.order_id}{suffix}"


def _export_mp4(settings: Settings, source_path: Path, target_path: Path) -> Path | None:
    try:
        ffmpeg = _find_executable("ffmpeg")
    except FileNotFoundError as exc:
        logger.warning("Could not export client session video: %s", exc)
        return None

    if settings.client_video_width < settings.client_video_height:
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
