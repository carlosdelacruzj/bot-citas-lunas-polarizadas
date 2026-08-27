from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings
from appointment_bot.db.whatsapp_automation import enqueue_daily_slot_summary_job
from appointment_bot.services.tiktok_description import generate_tiktok_publication
from appointment_bot.services.unique_slot_watermark import (
    prepare_daily_unique_slot_watermarks,
)

logger = logging.getLogger(__name__)
LIMA_TIMEZONE = ZoneInfo("America/Lima")
CONFIG_PATH = Path(".runtime/whatsapp-daily-summary/config.json")
MONTH_NAMES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def enqueue_daily_slot_summary(
    settings: Settings,
    *,
    report_date: date | None = None,
    retry_sequence: int | None = None,
) -> bool:
    effective_date = report_date or datetime.now(LIMA_TIMEZONE).date()
    recipient_phone = _configured_recipient_phone()
    if recipient_phone is None:
        logger.info("Daily WhatsApp slot summary is not configured.")
        return False

    public_whatsapp = _configured_public_whatsapp()
    attachment_paths = prepare_daily_unique_slot_watermarks(
        settings,
        effective_date,
        public_whatsapp=public_whatsapp,
    )
    message_text = _daily_summary_message(effective_date)
    publication_text = generate_tiktok_publication(
        effective_date,
        public_whatsapp=public_whatsapp,
    )
    created = enqueue_daily_slot_summary_job(
        report_date=effective_date,
        recipient_phone=recipient_phone,
        message_text=message_text,
        publication_text=publication_text,
        attachment_paths=attachment_paths,
        retry_sequence=retry_sequence,
        settings=settings,
    )
    if created:
        logger.info(
            "Daily WhatsApp slot summary queued: date=%s images=%s",
            effective_date.isoformat(),
            len(attachment_paths),
        )
    else:
        logger.info(
            "Daily WhatsApp slot summary already exists: date=%s",
            effective_date.isoformat(),
        )
    return created


def _configured_recipient_phone() -> str | None:
    payload = _daily_summary_config()
    if payload is None:
        return None
    recipient_phone = str(payload.get("recipient_phone") or "").strip()
    if not recipient_phone:
        raise ValueError(
            "La configuracion del resumen diario no contiene recipient_phone."
        )
    return recipient_phone


def _configured_public_whatsapp() -> str:
    payload = _daily_summary_config()
    if payload is None:
        raise ValueError("El resumen diario de WhatsApp no esta configurado.")
    public_whatsapp = str(payload.get("public_whatsapp") or "").strip()
    if not public_whatsapp:
        raise ValueError(
            "La configuracion del resumen diario no contiene public_whatsapp."
        )
    return public_whatsapp


def _daily_summary_config() -> dict[str, object] | None:
    if not CONFIG_PATH.is_file():
        return None
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(
            "No se pudo leer la configuracion del resumen diario de WhatsApp."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            "La configuracion del resumen diario debe contener un objeto JSON."
        )
    if payload.get("enabled") is False:
        return None
    return payload


def _daily_summary_message(report_date: date) -> str:
    return (
        "Resumen de cupos únicos hoy "
        f"{report_date.day} de {MONTH_NAMES[report_date.month]} de {report_date.year}"
    )


__all__ = ["enqueue_daily_slot_summary"]
