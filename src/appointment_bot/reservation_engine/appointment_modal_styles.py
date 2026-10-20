import logging

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

logger = logging.getLogger(__name__)

APPOINTMENT_MODAL_CSS_HEALTHY = "healthy"
APPOINTMENT_MODAL_CSS_FALLBACK_APPLIED = "fallback_applied"
APPOINTMENT_MODAL_CSS_UNKNOWN = "unknown"

_COMPATIBILITY_STYLE_ID = "appointment-bot-modal-css-compatibility"
_COMPATIBILITY_CSS = """
.modalBackground {
    background-color: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(3px);
}

.modal-panel {
    width: 900px;
    max-width: 95%;
    background: #fff;
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
    animation: appointmentBotModalShow 0.25s ease;
}

.modal-header-custom {
    background: linear-gradient(135deg, #104938, #104938);
    color: white;
    padding: 20px 30px;
}

.modal-header-custom h4,
.modal-header-custom i {
    color: white;
}

.modal-body-custom {
    padding: 30px;
    background: #f8f9fc;
}

.modal-footer-custom {
    padding: 18px 30px;
    text-align: right;
    background: white;
    border-top: 1px solid #eaeaea;
}

@keyframes appointmentBotModalShow {
    from {
        opacity: 0;
        transform: translateY(-15px) scale(0.97);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}
""".strip()


def ensure_appointment_modal_styles(page: Page) -> str:
    """Restore the former portal modal styles only for the known broken signature."""
    try:
        result = page.evaluate(
            """({styleId, compatibilityCss}) => {
                let existing = document.getElementById(styleId);
                if (existing?.sheet) existing.sheet.disabled = true;
                else {
                    existing?.remove();
                    existing = null;
                }

                const panel = document.querySelector("#MainContent_PanelCitas.modal-panel");
                const header = panel?.querySelector(".modal-header-custom");
                const body = panel?.querySelector(".modal-body-custom");
                if (!panel || !header || !body) {
                    existing?.remove();
                    return {status: "unknown", reason: "modal_structure_missing"};
                }

                const panelStyle = getComputedStyle(panel);
                const headerStyle = getComputedStyle(header);
                const bodyStyle = getComputedStyle(body);
                const transparent = value => (
                    value === "transparent" || value === "rgba(0, 0, 0, 0)"
                );
                const zeroPadding = value => value === "0px";
                const zeroRadius = value => value === "0px";
                const nativeHealthy = (
                    !transparent(panelStyle.backgroundColor)
                    && !zeroRadius(panelStyle.borderRadius)
                    && panelStyle.overflow === "hidden"
                    && panelStyle.boxShadow !== "none"
                    && !zeroPadding(headerStyle.padding)
                    && !zeroPadding(bodyStyle.padding)
                );
                const knownBroken = (
                    transparent(panelStyle.backgroundColor)
                    && zeroRadius(panelStyle.borderRadius)
                    && panelStyle.overflow === "visible"
                    && panelStyle.boxShadow === "none"
                    && zeroPadding(headerStyle.padding)
                    && zeroPadding(bodyStyle.padding)
                );

                if (nativeHealthy) {
                    existing?.remove();
                    document.documentElement.dataset.appointmentModalCss = "healthy";
                    return {status: "healthy", reason: "portal_styles_present"};
                }
                if (!knownBroken) {
                    existing?.remove();
                    document.documentElement.dataset.appointmentModalCss = "unknown";
                    return {status: "unknown", reason: "unrecognized_portal_styles"};
                }

                const style = existing || document.createElement("style");
                style.id = styleId;
                style.textContent = compatibilityCss;
                if (existing) existing.sheet.disabled = false;
                else document.head.appendChild(style);
                document.documentElement.dataset.appointmentModalCss = "fallback_applied";
                return {status: "fallback_applied", reason: "known_broken_signature"};
            }""",
            {
                "styleId": _COMPATIBILITY_STYLE_ID,
                "compatibilityCss": _COMPATIBILITY_CSS,
            },
        )
    except PlaywrightError as exc:
        logger.warning("Appointment modal CSS status=unknown reason=evaluation_failed: %s", exc)
        return APPOINTMENT_MODAL_CSS_UNKNOWN

    status = str(result.get("status") or APPOINTMENT_MODAL_CSS_UNKNOWN)
    reason = str(result.get("reason") or "not_reported")
    logger.info("Appointment modal CSS status=%s reason=%s", status, reason)
    return status
