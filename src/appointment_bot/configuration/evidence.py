from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvidenceSettings:
    screenshot_on_error: bool
    screenshot_on_relevant_result: bool
    screenshot_device_scale_factor: int
    client_video_width: int
    client_video_height: int
    record_client_sessions: bool
    record_client_video_final_mp4: bool
    cleanup_retention_days: int
    screenshots_dir: Path
    client_videos_dir: Path
    artifact_prefix: str
