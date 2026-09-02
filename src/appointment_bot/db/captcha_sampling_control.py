from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _settings, init_database

MIN_SAMPLE_LIMIT = 2
MAX_SAMPLE_LIMIT = 50
ESTIMATED_SECONDS_PER_EXTRA_SAMPLE = 0.4


@dataclass(frozen=True)
class CaptchaSamplingControl:
    enabled: bool
    sample_limit: int
    updated_at: datetime | None
    updated_by: str
    source: str = "database"

    @property
    def effective_sample_limit(self) -> int:
        return self.sample_limit if self.enabled else 1

    @property
    def estimated_extra_seconds(self) -> float:
        return round(
            max(self.effective_sample_limit - 1, 0)
            * ESTIMATED_SECONDS_PER_EXTRA_SAMPLE,
            1,
        )


def get_captcha_sampling_control(
    settings: Settings | None = None,
) -> CaptchaSamplingControl:
    resolved_settings = _settings(settings)
    init_database(resolved_settings)
    with _connection(_database_url(resolved_settings)) as connection:
        row = connection.execute(
            """
            SELECT enabled, sample_limit, updated_at, updated_by
            FROM captcha_sampling_control
            WHERE id = 1
            """
        ).fetchone()
    if row is None:
        return _environment_fallback(resolved_settings)
    return CaptchaSamplingControl(
        enabled=bool(row["enabled"]),
        sample_limit=int(row["sample_limit"]),
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
    )


def update_captcha_sampling_control(
    *,
    enabled: bool,
    sample_limit: int,
    updated_by: str,
    settings: Settings | None = None,
) -> CaptchaSamplingControl:
    _validate(enabled, sample_limit)
    resolved_settings = _settings(settings)
    init_database(resolved_settings)
    now = datetime.now(UTC)
    actor = updated_by.strip()[:64] or "admin_api"
    with _connection(_database_url(resolved_settings)) as connection:
        row = connection.execute(
            """
            INSERT INTO captcha_sampling_control (
                id, enabled, sample_limit, updated_at, updated_by
            )
            VALUES (1, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                sample_limit = EXCLUDED.sample_limit,
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by
            RETURNING enabled, sample_limit, updated_at, updated_by
            """,
            (enabled, sample_limit, now, actor),
        ).fetchone()
    return CaptchaSamplingControl(
        enabled=bool(row["enabled"]),
        sample_limit=int(row["sample_limit"]),
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
    )


def _environment_fallback(settings: Settings) -> CaptchaSamplingControl:
    configured_limit = max(int(settings.reservation_captcha_sample_limit), 1)
    enabled = configured_limit > 1
    sample_limit = min(
        max(configured_limit, MIN_SAMPLE_LIMIT),
        MAX_SAMPLE_LIMIT,
    )
    return CaptchaSamplingControl(
        enabled=enabled,
        sample_limit=sample_limit,
        updated_at=None,
        updated_by="environment",
        source="environment_fallback",
    )


def _validate(enabled: bool, sample_limit: int) -> None:
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean.")
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int):
        raise ValueError("sample_limit must be an integer.")
    if not MIN_SAMPLE_LIMIT <= sample_limit <= MAX_SAMPLE_LIMIT:
        raise ValueError(
            f"sample_limit must be between {MIN_SAMPLE_LIMIT} and {MAX_SAMPLE_LIMIT}."
        )
