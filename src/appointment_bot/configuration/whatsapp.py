from dataclasses import dataclass
from datetime import time as datetime_time


@dataclass(frozen=True)
class WhatsappSettings:
    appointment_reminders_time: datetime_time
    appointment_reminders_summary_grace_minutes: int
    appointment_reminders_reconcile_seconds: int
    appointment_reminders_send_interval_seconds: int
    appointment_reminders_daily_limit: int
