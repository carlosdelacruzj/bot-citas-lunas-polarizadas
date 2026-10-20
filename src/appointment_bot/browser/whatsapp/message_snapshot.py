from __future__ import annotations

from playwright.sync_api import Page

# One DOM read avoids a browser round trip for every bubble, icon and label.
OUTGOING_SNAPSHOT_SCRIPT = r"""({excluded}) => {
    const visible = element => {
        const style = getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden'
            && element.getClientRects().length > 0;
    };
    const seen = new Set(excluded);
    const records = [];
    const selectors = ['div.message-out', 'div[data-id^="true_"]',
        '[data-testid="msg-container"]'];
    for (const selector of selectors) {
        const messages = document.querySelectorAll(selector);
        if (!messages.length) continue;
        for (const message of messages) {
            const owner = message.closest('[data-id]');
            const id = owner?.getAttribute('data-id');
            if (!id || seen.has('data-id:' + id)) continue;
            const outgoing = !!message.closest('.message-out, [data-id^="true_"]');
            if (!outgoing) continue;
            seen.add('data-id:' + id);
            const markers = [...message.querySelectorAll(
                '[data-icon], svg:has(title), [aria-label], [role="progressbar"], '
                + '[class*="wds-ic-"]')].filter(visible);
            let pending = false, confirmed = false;
            for (const marker of markers) {
                const icon = marker.getAttribute('data-icon') || '';
                const title = marker.querySelector('title')?.textContent?.trim() || '';
                const classes = marker.getAttribute('class') || '';
                const label = (marker.getAttribute('aria-label') || '').normalize('NFKD')
                    .replace(/\p{M}/gu, '').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
                if (/time|error|retry|upload/.test(icon)
                    || /^(wds-ic-time|wds-ic-error)$/.test(title)
                    || /wds-ic-(time|error)/.test(classes)
                    || marker.getAttribute('role') === 'progressbar'
                    || /nosepudoenviar|reintentar|failed|notsent|retry/.test(label)) pending = true;
                if (/^msg-(check|dblcheck)(-|$)|dblcheck/.test(icon)
                    || /^wds-ic-(read|delivered|sent)$/.test(title)
                    || /wds-ic-(read|delivered|sent)/.test(classes)
                    || /^(enviado|entregado|leido|sent|delivered|read)$/.test(label)) {
                    confirmed = true;
                }
            }
            const copy = message.cloneNode(true);
            copy.querySelectorAll('img[alt]').forEach(image =>
                image.replaceWith(document.createTextNode(image.getAttribute('alt') || '')));
            records.push({signature: 'data-id:' + id, text: copy.textContent || '',
                largeImage: [...message.querySelectorAll('img')].some(image => {
                    const box = image.getBoundingClientRect();
                    return visible(image) && box.width >= 100 && box.height >= 100;
                }),
                state: pending ? 'pending' : confirmed ? 'confirmed' : 'unknown',
                expandable: [...message.querySelectorAll('[role="button"], button, span')]
                    .some(node => visible(node) && /^(Leer m[aá]s|Read more)$/i
                        .test(node.textContent.trim()))});
        }
        break;
    }
    return records;
}"""


def outgoing_snapshot(page: Page, excluded: set[str] | None = None) -> list[dict]:
    return page.evaluate(OUTGOING_SNAPSHOT_SCRIPT, {"excluded": list(excluded or ())})
