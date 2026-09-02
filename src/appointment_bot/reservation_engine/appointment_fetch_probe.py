from __future__ import annotations

import logging

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.reservation_engine.appointment_contracts import (
    DATE_SELECTOR,
    HOUR_SELECTOR,
    SITE_SELECTOR,
    SLOTS_LABEL_ID,
    AppointmentSnapshot,
)

logger = logging.getLogger(__name__)


def read_fetch_probe_appointment_snapshot(page: Page):
    try:
        data = page.evaluate(
            """async ({ siteSelector, dateSelector, hourSelector, slotsLabelId }) => {
                const ids = {
                    site: siteSelector.slice(1),
                    date: dateSelector.slice(1),
                    hour: hourSelector.slice(1),
                    slots: slotsLabelId
                };
                const names = {
                    site: "ctl00$MainContent$idUcitas$cbosede",
                    date: "ctl00$MainContent$idUcitas$cboFecha"
                };
                const form = (
                    document.getElementById("form1")
                    || document.forms.form1
                    || document.forms[0]
                );
                const siteEl = document.querySelector(siteSelector);
                if (!form || !siteEl) return null;

                const action = form.getAttribute("action") || location.href;
                const url = new URL(action, location.href).toString();
                const setFormValue = (targetForm, name, value) => {
                    let element = targetForm.elements[name];
                    if (!element) {
                        element = targetForm.ownerDocument.createElement("input");
                        element.type = "hidden";
                        element.name = name;
                        targetForm.appendChild(element);
                    }
                    element.value = value || "";
                };
                const getForm = doc => (
                    doc.getElementById("form1") || doc.forms.form1 || doc.forms[0]
                );
                const postForm = async (doc, eventTarget, changes) => {
                    const targetForm = getForm(doc);
                    if (!targetForm) throw new Error("form1 not found");
                    Object.entries(changes || {}).forEach(([name, value]) => {
                        setFormValue(targetForm, name, value);
                    });
                    setFormValue(targetForm, "__EVENTTARGET", eventTarget);
                    setFormValue(targetForm, "__EVENTARGUMENT", "");
                    const response = await fetch(url, {
                        method: "POST",
                        body: new FormData(targetForm),
                        credentials: "include"
                    });
                    const html = await response.text();
                    return new DOMParser().parseFromString(html, "text/html");
                };
                const options = (doc, id) => {
                    const element = doc.getElementById(id);
                    if (!element) return [];
                    return Array.from(element.options).map(option => ({
                        text: (option.textContent || "").trim(),
                        value: option.value || "",
                        selected: option.selected
                    }));
                };
                const selectedText = items => {
                    const selected = items.find(option => option.selected);
                    return selected ? selected.text : "";
                };
                const isReal = option => {
                    const text = (option && option.text || "").trim().toLowerCase();
                    return Boolean(option && option.value)
                        && option.value !== "0"
                        && option.value !== "00"
                        && text
                        && !text.includes("sin cupos")
                        && !text.includes("seleccione");
                };
                const textById = (doc, id) => {
                    const element = doc.getElementById(id);
                    return element ? (element.textContent || "").trim() : "";
                };

                const siteValue = siteEl.value;
                const siteText = siteEl.options[siteEl.selectedIndex]
                    ? siteEl.options[siteEl.selectedIndex].text.trim()
                    : siteValue;
                const docDates = await postForm(document, names.site, {
                    [names.site]: siteValue
                });
                const dateOptions = options(docDates, ids.date);
                const realDates = dateOptions.filter(isReal);
                let hourOptions = [];
                let slots = "";
                if (realDates.length > 0) {
                    const firstDate = realDates[0];
                    const docHours = await postForm(docDates, names.date, {
                        [names.site]: siteValue,
                        [names.date]: firstDate.value
                    });
                    hourOptions = options(docHours, ids.hour);
                    slots = textById(docHours, ids.slots);
                }
                return {
                    siteOptions: options(document, ids.site)
                        .map(option => option.text)
                        .filter(Boolean),
                    dateOptions: dateOptions.map(option => option.text).filter(Boolean),
                    hourOptions: hourOptions.map(option => option.text).filter(Boolean),
                    site: siteText,
                    date: realDates[0] ? realDates[0].text : selectedText(dateOptions),
                    hour: selectedText(hourOptions),
                    slots,
                    personName: ""
                };
            }""",
            {
                "siteSelector": SITE_SELECTOR,
                "dateSelector": DATE_SELECTOR,
                "hourSelector": HOUR_SELECTOR,
                "slotsLabelId": SLOTS_LABEL_ID,
            },
        )
    except PlaywrightError as exc:
        logger.debug("Fetch appointment probe failed: %s", exc)
        return None

    if not data:
        return None

    snapshot = AppointmentSnapshot(
        site_options=list(data.get("siteOptions") or []),
        date_options=list(data.get("dateOptions") or []),
        hour_options=list(data.get("hourOptions") or []),
        site=str(data.get("site") or ""),
        date=str(data.get("date") or ""),
        hour=str(data.get("hour") or ""),
        slots=str(data.get("slots") or ""),
        person_name=str(data.get("personName") or ""),
    )
    logger.debug("Fetch appointment probe signature: %s", snapshot.signature())
    return snapshot
