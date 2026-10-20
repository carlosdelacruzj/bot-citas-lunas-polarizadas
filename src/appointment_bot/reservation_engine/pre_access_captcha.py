from __future__ import annotations

import logging
import threading

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.reservation_engine.appointment_contracts import (
    SITE_SELECTOR,
    AppointmentWorkflowCancelled,
    PortalContractChanged,
)
from appointment_bot.reservation_engine.reservation_captcha_math import (
    ensure_reservation_honeypot_empty,
    read_reservation_math_captcha,
    validate_reservation_math_captcha,
)
from appointment_bot.reservation_engine.reservation_controls import (
    PRE_ACCESS_CAPTCHA_BUTTON_SELECTOR,
    PRE_ACCESS_CAPTCHA_INPUT_SELECTOR,
    PRE_ACCESS_CAPTCHA_QUESTION_SELECTOR,
    PRE_ACCESS_CAPTCHA_SERVER_BUTTON_SELECTOR,
    PRE_ACCESS_CAPTCHA_TOKEN_SELECTOR,
    PRE_ACCESS_CAPTCHA_VERIFIED_SELECTOR,
    RESERVATION_HONEYPOT_SELECTOR,
)

logger = logging.getLogger(__name__)


def resolve_pre_access_captcha(
    page: Page,
    *,
    cancel_event: threading.Event | None = None,
    timeout: int = 15_000,
) -> bool:
    controls = {
        "answer": page.locator(PRE_ACCESS_CAPTCHA_INPUT_SELECTOR),
        "button": page.locator(PRE_ACCESS_CAPTCHA_BUTTON_SELECTOR),
        "server_button": page.locator(PRE_ACCESS_CAPTCHA_SERVER_BUTTON_SELECTOR),
        "token": page.locator(PRE_ACCESS_CAPTCHA_TOKEN_SELECTOR),
        "verified": page.locator(PRE_ACCESS_CAPTCHA_VERIFIED_SELECTOR),
        "honeypot": page.locator(RESERVATION_HONEYPOT_SELECTOR),
    }
    signature_names = ("answer", "button", "server_button", "verified")
    signature_counts = {name: controls[name].count() for name in signature_names}
    if not any(signature_counts.values()):
        return False

    all_counts = {name: locator.count() for name, locator in controls.items()}
    if any(count != 1 for count in all_counts.values()):
        raise PortalContractChanged(
            "Cambio de seguridad del portal: la barrera CAPTCHA previa ya no tiene "
            "una estructura unica reconocible."
        )

    answer_field = controls["answer"].first
    verify_button = controls["button"].first
    verified_field = controls["verified"].first
    token_field = controls["token"].first
    site_field = page.locator(SITE_SELECTOR).first

    ensure_reservation_honeypot_empty(page)

    verified_value = verified_field.input_value()
    if verified_value == "1":
        if not token_field.input_value():
            raise PortalContractChanged(
                "Cambio de seguridad del portal: falta el token de una verificacion "
                "previa ya confirmada."
            )
        try:
            site_field.wait_for(state="visible", timeout=timeout)
        except PlaywrightTimeoutError as exc:
            raise PortalContractChanged(
                "Cambio de seguridad del portal: la verificacion previa figura confirmada "
                "pero la sede sigue oculta."
            ) from exc
        return True
    if verified_value not in {"", "0"}:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el estado inicial del CAPTCHA previo no es "
            "reconocible."
        )
    if not answer_field.is_visible() or not verify_button.is_visible():
        raise PortalContractChanged(
            "Cambio de seguridad del portal: los controles visibles del CAPTCHA previo "
            "no coinciden con el contrato validado."
        )
    if answer_field.input_value() or token_field.input_value():
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el CAPTCHA previo contiene valores iniciales "
            "inesperados."
        )

    challenge = read_reservation_math_captcha(
        page,
        selector=PRE_ACCESS_CAPTCHA_QUESTION_SELECTOR,
    )
    if challenge is None:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el CAPTCHA previo no contiene la suma HTML "
            "esperada."
        )
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de verificar el CAPTCHA previo."
        )

    logger.info("Solving the recognized pre-access HTML math CAPTCHA locally")
    answer_field.fill(challenge.answer, timeout=timeout)
    validate_reservation_math_captcha(
        page,
        expected_signature=challenge.signature,
        selector=PRE_ACCESS_CAPTCHA_QUESTION_SELECTOR,
    )
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de enviar el CAPTCHA previo."
        )

    try:
        verify_button.click(timeout=timeout)
        page.wait_for_function(
            'selector => document.querySelector(selector)?.value === "1"',
            arg=PRE_ACCESS_CAPTCHA_VERIFIED_SELECTOR,
            timeout=timeout,
        )
        site_field.wait_for(state="visible", timeout=timeout)
    except PlaywrightTimeoutError as exc:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: no confirmo el CAPTCHA previo ni habilito "
            "la sede dentro del limite seguro."
        ) from exc

    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico despues de verificar el CAPTCHA previo."
        )
    if verified_field.input_value() != "1":
        raise PortalContractChanged(
            "Cambio de seguridad del portal: la confirmacion del CAPTCHA previo es "
            "ambigua."
        )
    if not token_field.input_value():
        raise PortalContractChanged(
            "Cambio de seguridad del portal: falta el token confirmado del CAPTCHA previo."
        )
    ensure_reservation_honeypot_empty(page)
    logger.info("Pre-access HTML math CAPTCHA confirmed by the portal")
    return True
