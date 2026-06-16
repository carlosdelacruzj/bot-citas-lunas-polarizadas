from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from appointment_bot.config import Settings, load_settings


def make_settings(root: Path) -> Settings:
    with patch.dict(
        "os.environ",
        {
            "TARGET_URL": "https://example.invalid",
            "CONTINUOUS_WORKER_ENABLED": "true",
            "AUTO_RESERVE": "true",
        },
        clear=False,
    ):
        settings = load_settings(require_login=False)
    return replace(
        settings,
        database_path=root / "data" / "appointment_bot.sqlite",
        logs_dir=root / "logs",
        screenshots_dir=root / "screenshots",
        diagnostics_dir=root / "diagnostics",
        state_dir=root / "state",
        cleanup_retention_days=14,
    )
