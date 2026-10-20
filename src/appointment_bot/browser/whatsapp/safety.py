from __future__ import annotations

from playwright.sync_api import Page

from appointment_bot.browser.whatsapp.evidence import _save_whatsapp_debug_screenshot


def require_clear_outgoing_queue(page: Page, *, evidence_prefix: str) -> None:
    unsettled = page.evaluate(r"""() => {
        const visible = element => {
            const style = getComputedStyle(element);
            return style.visibility !== 'hidden' && style.display !== 'none'
                && element.getClientRects().length > 0;
        };
        const messages = document.querySelectorAll(
            '.message-out, [data-id^="true_"], [data-testid="msg-container"]'
        );
        const markers = [
            '[data-icon="msg-time"]', '[data-icon^="msg-time-"]',
            '[data-icon*="error"]', '[data-icon*="retry"]',
            '[data-icon*="upload"]', '[role="progressbar"]',
            '[class*="wds-ic-time"]', '[class*="wds-ic-error"]',
            '[aria-label*="No se pudo enviar" i]', '[aria-label*="Reintentar" i]',
            '[aria-label*="Failed" i]', '[aria-label*="Not sent" i]',
            '[aria-label*="Retry" i]'
        ].join(',');
        const pendingSvg = message => Array.from(message.querySelectorAll('svg'))
            .some(svg => visible(svg) && ['wds-ic-time', 'wds-ic-error'].includes(
                svg.querySelector('title')?.textContent?.trim()
            ));
        const clock = message => pendingSvg(message)
            || Array.from(message.querySelectorAll(
                '[data-icon="msg-time"], [data-icon^="msg-time-"], [class*="wds-ic-time"]'
            )).some(visible);
        const outgoing = message => clock(message)
            || !!message.closest('.message-out, [data-id^="true_"]')
            || Array.from(message.querySelectorAll('[aria-label]')).some(label => {
                const value = (label.getAttribute('aria-label') || '').normalize('NFKD')
                    .replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
                return value === 'tu:' || value === 'you:';
            });
        return Array.from(messages).some(message => visible(message) && outgoing(message)
            && (Array.from(message.querySelectorAll(markers)).some(visible)
                || pendingSvg(message)));
    }""")
    if unsettled:
        path = _save_whatsapp_debug_screenshot(page, f"{evidence_prefix}-outgoing-queue-blocked")
        raise RuntimeError(
            "El chat tiene envios anteriores pendientes, cargando o con error. "
            "No se iniciara otra accion de envio. Revisa esos mensajes en WhatsApp "
            f"antes de recuperar lo faltante. Evidencia local: {path}."
        )
