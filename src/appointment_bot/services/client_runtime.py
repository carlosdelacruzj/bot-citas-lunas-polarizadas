import hashlib
from dataclasses import replace

from appointment_bot.config import Settings
from appointment_bot.domain import ResultStatus, RunReport
from appointment_bot.services.database import Client


def settings_with_client_state_dir(settings: Settings, client: Client) -> Settings:
    safe_client_id = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in client.client_id
    )
    digest = hashlib.sha256(client.client_id.encode("utf-8")).hexdigest()[:10]
    return replace(
        settings,
        state_dir=settings.state_dir / "clients" / f"{safe_client_id}-{digest}",
    )


def report_is_programmed(report: RunReport) -> bool:
    details = report.details or {}
    status = str(details.get("estado") or "").strip().lower()
    return report.status == ResultStatus.COMPLETED and status == "programado"
