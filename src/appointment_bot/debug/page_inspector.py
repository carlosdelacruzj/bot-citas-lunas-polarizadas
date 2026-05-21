import logging

from playwright.sync_api import Page

logger = logging.getLogger(__name__)

SENSITIVE_FIELD_PARTS = [
    "dni",
    "documento",
    "email",
    "mail",
    "paterno",
    "materno",
    "nombres",
    "password",
    "placa",
    "serie",
    "motor",
    "usuario",
    "username",
]


def inspect_page(page: Page, *, label: str) -> None:
    logger.info("=== Page inspection: %s ===", label)
    logger.info("URL: %s", page.url)
    logger.info("Title: %s", page.title())

    _log_elements(
        page,
        "select",
        """elements => elements.map((element, index) => ({
            index,
            id: element.id,
            name: element.name,
            text: element.innerText,
            value: element.value
        }))""",
    )
    _log_elements(
        page,
        "input",
        """elements => elements.map((element, index) => ({
            index,
            type: element.type,
            id: element.id,
            name: element.name,
            value: element.type === "password" ? "***" : element.value,
            alt: element.alt,
            src: element.src,
            onclick: element.getAttribute("onclick")
        }))""",
    )
    _log_elements(
        page,
        "button",
        """elements => elements.map((element, index) => ({
            index,
            type: element.type,
            id: element.id,
            name: element.name,
            text: element.innerText,
            onclick: element.getAttribute("onclick")
        }))""",
    )
    _log_elements(
        page,
        "a",
        """elements => elements.map((element, index) => ({
            index,
            id: element.id,
            text: element.innerText,
            href: element.href,
            onclick: element.getAttribute("onclick")
        }))""",
    )
    logger.info("=== End page inspection: %s ===", label)


def _log_elements(page: Page, selector: str, script: str) -> None:
    elements = page.locator(selector).evaluate_all(script)
    logger.info("%s count: %s", selector, len(elements))
    for element in elements:
        _mask_sensitive_element_values(element)
        for key, value in list(element.items()):
            if isinstance(value, str) and len(value) > 250:
                element[key] = f"{value[:250]}...<truncated>"
        logger.info("%s: %s", selector, element)


def _mask_sensitive_element_values(element: dict) -> None:
    field_id = str(element.get("id") or "").lower()
    field_name = str(element.get("name") or "").lower()
    field_key = f"{field_id} {field_name}"

    if any(part in field_key for part in SENSITIVE_FIELD_PARTS):
        if "value" in element and element["value"]:
            element["value"] = "***"
