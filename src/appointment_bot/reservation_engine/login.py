import logging

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.config import Settings

logger = logging.getLogger(__name__)

DOCUMENT_TYPE_SELECTOR = "select#DdlDocumento"
DOCUMENT_TYPE_VALUE = "1"  # DNI
USERNAME_SELECTOR = (
    'input[name="username"], input[name="email"], input[type="email"], input[type="text"]'
)
PASSWORD_SELECTOR = 'input[name="password"], input[type="password"]'
SUBMIT_SELECTOR = (
    'button[type="submit"], input[type="submit"], '
    'button:has-text("Ingresar"), button:has-text("Login")'
)
POST_LOGIN_SELECTOR = (
    'input[type="image"][onclick*="gvProgramacion"], '
    'a[id^="MainContent_gvProgramacion_btnAccion_"][href*="__doPostBack"], '
    'input#MainContent_BtnNuevo'
)
INVALID_CREDENTIAL_TEXTS = (
    "clave incorrecta o no se ha registrado",
    "clave incorrecta",
)


class InvalidPortalCredentials(RuntimeError):
    pass


def login(page: Page, settings: Settings) -> None:
    timeout = settings.login_timeout_seconds * 1_000
    logger.info("Opening target URL")
    page.goto(settings.target_url, wait_until="domcontentloaded", timeout=timeout)

    logger.info("Filling login form")
    try:
        page.locator(DOCUMENT_TYPE_SELECTOR).select_option(DOCUMENT_TYPE_VALUE, timeout=timeout)
        page.locator(USERNAME_SELECTOR).first.fill(settings.login_username, timeout=timeout)
        page.locator(PASSWORD_SELECTOR).first.fill(settings.login_password, timeout=timeout)
        page.locator(SUBMIT_SELECTOR).first.click(timeout=timeout)
        outcome = page.wait_for_function(
            """({ selector, rejectionTexts }) => {
                const bodyText = (document.body ? document.body.innerText : "").toLowerCase();
                if (rejectionTexts.some(text => bodyText.includes(text))) return "rejected";
                const postLogin = document.querySelector(selector);
                if (postLogin && postLogin.getClientRects().length) return "completed";
                return false;
            }""",
            arg={
                "selector": POST_LOGIN_SELECTOR,
                "rejectionTexts": list(INVALID_CREDENTIAL_TEXTS),
            },
            timeout=timeout,
        ).json_value()
        if outcome == "rejected":
            raise InvalidPortalCredentials(
                "El portal rechazo la clave: clave incorrecta o cuenta no registrada."
            )
        page.locator(POST_LOGIN_SELECTOR).first.wait_for(state="visible", timeout=timeout)
    except InvalidPortalCredentials:
        raise
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "Could not complete login with the configured selectors. "
            "Update DOCUMENT_TYPE_SELECTOR, USERNAME_SELECTOR, PASSWORD_SELECTOR, "
            "SUBMIT_SELECTOR or POST_LOGIN_SELECTOR in flows/login.py."
        ) from exc

    logger.info("Login flow completed")
