from __future__ import annotations

from appointment_bot.config import Settings
from appointment_bot.db.whatsapp_automation import (
    RegistrationNoticeType,
    enqueue_registration_notice_job,
)


def enqueue_registration_notice(
    *,
    order_id: str,
    preflight_cycle: int,
    notice_type: RegistrationNoticeType,
    recipient_phone: str | None,
    recipient_username: str | None,
    display_name: str | None,
    settings: Settings,
) -> bool:
    if not recipient_phone and not recipient_username:
        return False
    return enqueue_registration_notice_job(
        order_id=order_id,
        preflight_cycle=preflight_cycle,
        notice_type=notice_type,
        recipient_phone=recipient_phone,
        recipient_username=recipient_username,
        message_text=registration_notice_text(notice_type, display_name),
        settings=settings,
    )


def registration_notice_text(
    notice_type: RegistrationNoticeType,
    display_name: str | None,
) -> str:
    greeting = _greeting(display_name)
    if notice_type == "monitoring_started":
        return "\n\n".join(
            [
                greeting,
                "Pudimos ingresar correctamente y verificar tu solicitud ✅",
                "Tu disponibilidad quedó registrada y desde ahora comenzaremos "
                "con el monitoreo.",
                "Intentaremos reservar la fecha más próxima que aparezca dentro de "
                "las condiciones indicadas. Te escribiremos apenas consigamos la cita.",
            ]
        )
    if notice_type == "no_pending_request":
        return "\n\n".join(
            [
                greeting,
                "Pudimos ingresar correctamente, pero no encontramos una solicitud "
                "pendiente para reservar.",
                "Por favor, revisa si el trámite fue registrado y confírmanos cuando "
                "aparezca. Luego realizaremos una nueva validación.",
            ]
        )
    if notice_type == "invalid_credentials":
        return "\n\n".join(
            [
                greeting,
                "No pudimos validar el acceso con los datos registrados.",
                "Por seguridad realizamos un solo intento para evitar el bloqueo "
                "temporal de tu cuenta.",
                "Por favor, revisa el tipo y número de documento y la contraseña, y "
                "confírmanos los datos correctos para volver a validar.",
            ]
        )
    raise ValueError(f"Unsupported registration notice type: {notice_type}")


def _greeting(display_name: str | None) -> str:
    name = " ".join((display_name or "").split())
    return f"Hola, {name} 👋" if name else "Hola 👋"


__all__ = ["enqueue_registration_notice", "registration_notice_text"]
