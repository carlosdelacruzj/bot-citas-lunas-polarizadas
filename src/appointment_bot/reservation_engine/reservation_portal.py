from __future__ import annotations

import logging

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

CONFIRMATION_TEXTS = [
    "cita ha sido registrado",
    "cita ha sido registrada",
    "registrado satisfactoriamente",
    "registrada satisfactoriamente",
    "reservada con exito",
    "reservado con exito",
]
CAPTCHA_REJECTION_TEXTS = [
    "captcha incorrecto",
    "captcha invalido",
    "captcha valido",
    "codigo de seguridad incorrecto",
    "codigo de verificacion incorrecto",
    "ingrese el codigo valido del captcha",
]
SLOT_LOST_TEXTS = [
    "cupo ya no disponible",
    "cupo no disponible",
    "no existe cupos",
    "seleccione otra fecha",
    "ya no hay cupos",
    "sin cupos disponibles",
]
SUBMISSION_REJECTION_TEXTS = [
    "no se pudo registrar la cita",
    "no fue posible registrar la cita",
    "solicitud rechazada",
    "operacion no permitida",
]


def wait_for_reservation_submission_outcome(page: Page, *, timeout: int = 10_000) -> str:
    outcome_texts = {
        "confirmed": CONFIRMATION_TEXTS,
        "captcha_invalid": CAPTCHA_REJECTION_TEXTS,
        "slot_lost": SLOT_LOST_TEXTS,
        "rejected": SUBMISSION_REJECTION_TEXTS,
    }
    try:
        return str(
            page.wait_for_function(
                """groups => {
                    const normalize = value => (value || "")
                        .toLowerCase()
                        .normalize("NFD")
                        .replace(/[\\u0300-\\u036f]/g, "");
                    const text = normalize(document.body ? document.body.innerText : "");
                    for (const [outcome, values] of Object.entries(groups)) {
                        if (values.some(value => text.includes(normalize(value)))) return outcome;
                    }
                    return false;
                }""",
                arg=outcome_texts,
                timeout=timeout,
            ).json_value()
        )
    except PlaywrightTimeoutError:
        return "unknown"


def dismiss_reservation_confirmation(page: Page) -> None:
    logger.info("Trying to dismiss reservation confirmation")
    selectors = [
        ".swal2-confirm",
        "button:has-text('OK')",
        "button:has-text('Aceptar')",
        "button:has-text('Salir')",
        "button:has-text('Cerrar')",
        "input[type='button'][value='OK']",
        "input[type='button'][value='Aceptar']",
        "input[type='button'][value='Salir']",
        "input[type='button'][value='Cerrar']",
    ]
    for selector in selectors:
        control = page.locator(selector).first
        try:
            if control.count() == 0 or not control.is_visible(timeout=1_000):
                continue

            control.click(timeout=5_000)
            page.wait_for_timeout(1_000)
            logger.info("Dismissed reservation confirmation using selector %s", selector)
            return
        except PlaywrightError as exc:
            logger.info("Could not dismiss confirmation with selector %s: %s", selector, exc)

    logger.info("No reservation confirmation control was dismissed")
