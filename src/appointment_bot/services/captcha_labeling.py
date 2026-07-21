from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

LABEL_FIELDS = ("filename", "answer", "status", "labeled_at_utc", "updated_at_utc")


@dataclass(frozen=True)
class CaptchaLabelingProgress:
    completed: int
    total: int

    @property
    def pending(self) -> int:
        return max(0, self.total - self.completed)

    @property
    def percentage(self) -> float:
        return self.completed * 100 / self.total if self.total else 0.0


class CaptchaLabelStore:
    def __init__(self, images_dir: Path, labels_path: Path) -> None:
        self.images_dir = images_dir.resolve()
        self.labels_path = labels_path.resolve()
        self._lock = Lock()

    @classmethod
    def from_environment(cls) -> CaptchaLabelStore:
        repository_root = Path(__file__).resolve().parents[3]
        default_project = repository_root.parent / "test-captcha"
        images_dir = Path(
            os.getenv("TELEGRAM_CAPTCHA_IMAGES_DIR", "").strip()
            or default_project / "captchas_reales_sin_etiquetar"
        )
        labels_path = Path(
            os.getenv("TELEGRAM_CAPTCHA_LABELS_PATH", "").strip()
            or default_project / "outputs" / "captcha_labels_telegram.csv"
        )
        return cls(images_dir, labels_path)

    def validate(self) -> None:
        if not self.images_dir.is_dir():
            raise FileNotFoundError(f"Captcha images directory does not exist: {self.images_dir}")
        if not self.image_paths():
            raise FileNotFoundError(f"No numbered PNG images found in: {self.images_dir}")
        self.labels_path.parent.mkdir(parents=True, exist_ok=True)

    def image_paths(self) -> list[Path]:
        paths = [
            path
            for path in self.images_dir.glob("*.png")
            if path.is_file() and path.stem.isdigit()
        ]
        return sorted(paths, key=lambda path: int(path.stem))

    def next_pending(self) -> Path | None:
        with self._lock:
            completed = set(self._read_labels_unlocked())
            return next((path for path in self.image_paths() if path.name not in completed), None)

    def progress(self) -> CaptchaLabelingProgress:
        with self._lock:
            image_names = {path.name for path in self.image_paths()}
            completed = image_names.intersection(self._read_labels_unlocked())
            return CaptchaLabelingProgress(completed=len(completed), total=len(image_names))

    def save_answer(self, image_path: Path, answer: str) -> CaptchaLabelingProgress:
        resolved_image = image_path.resolve()
        if resolved_image.parent != self.images_dir or not resolved_image.is_file():
            raise ValueError("Captcha image is outside the configured collection.")
        normalized_answer = answer.strip().upper()
        if re.fullmatch(r"[A-Z0-9]{5}", normalized_answer) is None:
            raise ValueError("Captcha answer must contain exactly five letters or numbers.")

        with self._lock:
            rows = self._read_labels_unlocked()
            now = datetime.now(UTC).isoformat()
            previous = rows.get(resolved_image.name)
            rows[resolved_image.name] = {
                "filename": resolved_image.name,
                "answer": normalized_answer,
                "status": "completed",
                "labeled_at_utc": previous.get("labeled_at_utc", now) if previous else now,
                "updated_at_utc": now,
            }
            self._write_labels_unlocked(rows)
            image_names = {path.name for path in self.image_paths()}
            completed = image_names.intersection(rows)
            return CaptchaLabelingProgress(completed=len(completed), total=len(image_names))

    def _read_labels_unlocked(self) -> dict[str, dict[str, str]]:
        if not self.labels_path.exists():
            return {}
        with self.labels_path.open(newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            return {
                row["filename"]: row
                for row in reader
                if row.get("filename") and row.get("status") == "completed"
            }

    def _write_labels_unlocked(self, rows: dict[str, dict[str, str]]) -> None:
        temporary_path = self.labels_path.with_suffix(self.labels_path.suffix + ".tmp")
        with temporary_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=LABEL_FIELDS)
            writer.writeheader()
            writer.writerows(
                rows[filename]
                for filename in sorted(
                    rows,
                    key=lambda name: int(Path(name).stem),
                )
            )
        temporary_path.replace(self.labels_path)
