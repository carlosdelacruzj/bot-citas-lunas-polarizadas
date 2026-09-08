from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

from appointment_bot.reservation_engine.appointment_contracts import (
    DATE_SELECTOR,
    HOUR_SELECTOR,
    SITE_SELECTOR,
    AppointmentSnapshot,
)
from appointment_bot.utils.sanitization import normalize_option


def select_options_text(page: Page, selector: str) -> list[str]:
    return [option["text"] for option in select_options(page, selector) if option["text"]]


def select_options(page: Page, selector: str) -> list[dict[str, Any]]:
    select = page.locator(selector)
    if select.count() == 0:
        return []
    return select.locator("option").evaluate_all(
        """options => options.map(option => ({
            text: option.innerText.trim(),
            value: option.value,
            disabled: option.disabled,
            hidden: option.hidden
        }))"""
    )


def select_appointment_option(locator, value: str, *, allow_hidden: bool) -> None:
    if not allow_hidden:
        locator.select_option(value=value, timeout=15_000)
        return
    locator.evaluate(
        """(element, optionValue) => {
            element.value = optionValue;
            element.dispatchEvent(new Event("change", { bubbles: true }));
        }""",
        value,
    )


def real_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [option for option in options if is_real_appointment_option(option)]


def options_signature(options: list[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    return tuple((option["value"], option["text"]) for option in options)


def selected_option_text(page: Page, selector: str) -> str:
    select = page.locator(selector)
    if select.count() == 0:
        return ""
    return select.evaluate(
        """element => {
            const selected = element.options[element.selectedIndex];
            return selected ? selected.innerText.trim() : "";
        }"""
    )


def read_slots_value(page: Page) -> str:
    return page.evaluate(
        """() => {
            const normalize = value => (value || "").trim().toLowerCase();
            const directLabel = document.getElementById("MainContent_idUcitas_lblcupos");
            if (directLabel && directLabel.textContent.trim()) {
                return directLabel.textContent.trim();
            }
            const directInput = Array.from(document.querySelectorAll("input")).find(input => {
                const id = normalize(input.id);
                const name = normalize(input.name);
                return id.includes("cupo") || name.includes("cupo");
            });
            if (directInput && directInput.value.trim()) return directInput.value.trim();
            const labels = Array.from(document.querySelectorAll("label, span, th, td, div"));
            const cuposLabel = labels.find(element => normalize(element.innerText) === "cupos");
            if (!cuposLabel) return "";
            const container = cuposLabel.closest("tr, .row, div, fieldset, table")
                || document.body;
            const nearbyInput = Array.from(container.querySelectorAll("input"))
                .find(input => input.value.trim());
            if (nearbyInput) return nearbyInput.value.trim();
            return Array.from(container.querySelectorAll("span, label, div, td"))
                .map(element => (element.textContent || "").trim())
                .find(text => /^\\d+$/.test(text)) || "";
        }"""
    )


def read_person_name(page: Page) -> str:
    return page.evaluate(
        """() => {
            const normalize = value => (value || "").trim();
            const key = value => normalize(value).toLowerCase();
            const visibleValue = element => {
                const value = normalize(element.value || element.innerText || element.textContent);
                return value && value.length <= 120 ? value : "";
            };
            const fieldKey = element => key([
                element.id, element.name, element.placeholder,
                element.getAttribute("aria-label")
            ].join(" "));
            const controls = Array.from(document.querySelectorAll("input, textarea"))
                .filter(element => ![
                    "hidden", "password", "submit", "button", "image"
                ].includes(key(element.type)));
            const findValue = parts => {
                const control = controls.find(element => {
                    const controlKey = fieldKey(element);
                    return parts.some(part => controlKey.includes(part))
                        && visibleValue(element);
                });
                return control ? visibleValue(control) : "";
            };
            const names = findValue(["nombres", "nombre"]);
            const paternal = findValue(["paterno"]);
            const maternal = findValue(["materno"]);
            const surname = findValue(["apellidos", "apellido"]);
            const controlName = [names, paternal || surname, maternal]
                .filter(Boolean).join(" ").replace(/\\s+/g, " ").trim();
            if (controlName) return controlName;
            const lines = normalize(document.body ? document.body.innerText : "")
                .split("\\n").map(line => normalize(line)).filter(Boolean);
            const afterLabel = labels => {
                for (const label of labels) {
                    const normalizedLabel = label.toLowerCase();
                    for (let index = 0; index < lines.length; index += 1) {
                        const line = lines[index];
                        const lowerLine = line.toLowerCase();
                        if (lowerLine === normalizedLabel && lines[index + 1]) {
                            return lines[index + 1];
                        }
                        if (lowerLine.startsWith(`${normalizedLabel}:`)) {
                            return normalize(line.slice(label.length + 1));
                        }
                    }
                }
                return "";
            };
            const textNames = afterLabel(["Nombres", "Nombre"]);
            const textPaternal = afterLabel(["Apellido Paterno", "Paterno"]);
            const textMaternal = afterLabel(["Apellido Materno", "Materno"]);
            const textSurname = afterLabel(["Apellidos", "Apellido"]);
            return [textNames, textPaternal || textSurname, textMaternal]
                .filter(Boolean).join(" ").replace(/\\s+/g, " ").trim();
        }"""
    )


def read_appointment_snapshot(page: Page) -> AppointmentSnapshot:
    return AppointmentSnapshot(
        site_options=select_options_text(page, SITE_SELECTOR),
        date_options=select_options_text(page, DATE_SELECTOR),
        hour_options=select_options_text(page, HOUR_SELECTOR),
        site=selected_option_text(page, SITE_SELECTOR),
        date=selected_option_text(page, DATE_SELECTOR),
        hour=selected_option_text(page, HOUR_SELECTOR),
        slots=read_slots_value(page),
        person_name=read_person_name(page),
    )


def has_real_options(options: list[str]) -> bool:
    return any(is_real_appointment_option(option) for option in options)


def is_real_appointment_option(option: dict[str, Any] | str) -> bool:
    if isinstance(option, str):
        text, value_present, disabled, hidden = option, True, False, False
    else:
        text = str(option.get("text") or "")
        value_present = bool(option.get("value"))
        disabled = bool(option.get("disabled"))
        hidden = bool(option.get("hidden"))
    normalized = text.strip().lower()
    return (
        value_present
        and not disabled
        and not hidden
        and bool(normalized)
        and normalized != "sin cupos"
        and not normalized.startswith("seleccione")
    )


def same_option(actual: str, expected: str) -> bool:
    return normalize_option(actual) == normalize_option(expected)
