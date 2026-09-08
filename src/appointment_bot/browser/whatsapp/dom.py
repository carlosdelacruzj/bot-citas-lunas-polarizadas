from __future__ import annotations

import re
import unicodedata
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page


def _album_thumbnails(page: Page) -> list[Any]:
    controls = page.locator("[role='button']:has(img):has([data-icon='x-alt'])")
    thumbnails: list[Any] = []
    for index in range(controls.count()):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        box = control.bounding_box()
        if box and 48 <= box["width"] <= 96 and 48 <= box["height"] <= 96:
            thumbnails.append(control)
    return thumbnails


def _album_control_summary(page: Page) -> list[dict[str, object]]:
    controls = page.locator("button, [role='button']")
    viewport = page.viewport_size or {"width": 0, "height": 0}
    summary: list[dict[str, object]] = []
    for index in range(min(controls.count(), 160)):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        box = control.bounding_box()
        if box is None or box["y"] < viewport["height"] * 0.55:
            continue
        summary.append(
            {
                "index": index,
                "aria_label": control.get_attribute("aria-label"),
                "title": control.get_attribute("title"),
                "data_testid": control.get_attribute("data-testid"),
                "box": {key: round(value) for key, value in box.items()},
                "images": control.locator("img").count(),
                "canvases": control.locator("canvas").count(),
                "icons": [
                    control.locator("[data-icon]").nth(icon_index).get_attribute("data-icon")
                    for icon_index in range(min(control.locator("[data-icon]").count(), 3))
                ],
            }
        )
    return summary


def _attachment_menu_visible(page: Page) -> bool:
    media_option = page.get_by_text(
        re.compile(r"^(Fotos y v.deos|Photos and videos|Photos & videos)$", re.I)
    ).last
    if media_option.count() and media_option.is_visible():
        return True
    document_option = page.get_by_text(re.compile(r"^(Documento|Document)$", re.I)).last
    if document_option.count() and document_option.is_visible():
        return True
    document_label = page.locator(
        "[aria-label='Documento'], [aria-label='Document'], "
        "[title='Documento'], [title='Document']"
    ).last
    if document_label.count() and document_label.is_visible():
        return True
    return bool(page.locator("[role='menuitem']:visible").count())


def _attachment_option_container(option):
    for xpath in (
        "ancestor-or-self::*[@role='menuitem'][1]",
        "ancestor-or-self::*[@role='button'][1]",
        "ancestor-or-self::li[1]",
        "ancestor-or-self::*[@tabindex='0'][1]",
    ):
        candidate = option.locator(f"xpath={xpath}")
        if candidate.count() and candidate.first.is_visible():
            return candidate.first
    return option


def _image_file_input(page: Page, *, require_multiple: bool = False):
    inputs = page.locator("input[type='file']")
    for index in range(inputs.count() - 1, -1, -1):
        locator = inputs.nth(index)
        accept = (locator.get_attribute("accept") or "").casefold()
        allows_multiple = locator.evaluate("element => element.multiple")
        if "image" in accept and (not require_multiple or allows_multiple):
            return locator
    return None


def _document_file_input(page: Page):
    inputs = page.locator("input[type='file']")
    for index in range(inputs.count() - 1, -1, -1):
        locator = inputs.nth(index)
        accept = (locator.get_attribute("accept") or "").casefold()
        if "image" in accept or "video" in accept:
            continue
        if "pdf" in accept or "application" in accept or not accept:
            return locator
    return None


def _file_input_summary(page: Page) -> list[dict[str, object]]:
    inputs = page.locator("input[type='file']")
    summary: list[dict[str, object]] = []
    for index in range(inputs.count()):
        locator = inputs.nth(index)
        label = locator.locator("xpath=ancestor::li[1]")
        if not label.count():
            label = locator.locator("xpath=ancestor::*[@role='button'][1]")
        label_text = ""
        if label.count():
            try:
                label_text = label.inner_text(timeout=1_000)[:80]
            except PlaywrightError:
                label_text = ""
        summary.append(
            {
                "index": index,
                "accept": _safe_get_attribute(locator, "accept"),
                "multiple": _safe_get_attribute(locator, "multiple"),
                "label": label_text,
            }
        )
    return summary


def _attachment_menu_summary(page: Page) -> list[dict[str, object]]:
    controls = page.locator("[role='menu'] [role='button'], [role='menuitem'], [role='menu'] li")
    summary: list[dict[str, object]] = []
    for index in range(min(controls.count(), 20)):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        try:
            text = control.inner_text(timeout=1_000)[:80]
        except PlaywrightError:
            text = ""
        summary.append(
            {
                "text": text,
                "aria_label": _safe_get_attribute(control, "aria-label"),
                "inputs": _file_input_summary_from(control),
            }
        )
    return summary


def _file_input_summary_from(root) -> list[str | None]:
    inputs = root.locator("input[type='file']")
    return [_safe_get_attribute(inputs.nth(index), "accept") for index in range(inputs.count())]


def _locator_has_visible_match(locator) -> bool:
    for index in range(locator.count()):
        try:
            if locator.nth(index).is_visible():
                return True
        except PlaywrightError:
            continue
    return False


def _plain_text_ready(page: Page, expected: str) -> bool:
    editors = page.locator(
        "footer div[contenteditable='true'], "
        "div[data-testid='conversation-compose-box-input']"
    )
    for index in range(editors.count() - 1, -1, -1):
        text = _safe_text_content(editors.nth(index))
        if _same_editor_text(text, expected, require_full_match=True) or (
            "TikTok" in text and "citaspolarizadasperu" in text
        ):
            return True
    return False


def _normal_chat_composer_visible(page: Page) -> bool:
    composer = page.locator("div[data-testid='conversation-compose-box-input']").last
    return bool(composer.count() and composer.is_visible())


def _document_preview_visible(page: Page, names: list[str]) -> bool:
    document_icons = page.locator("[data-icon='media-document']")
    if any(document_icons.nth(index).is_visible() for index in range(document_icons.count())):
        return True
    for name in names:
        preview_text = page.get_by_text(name, exact=True)
        if any(preview_text.nth(index).is_visible() for index in range(preview_text.count())):
            return True
    return False


def _attachment_preview_visible(page: Page, names: list[str]) -> bool:
    close_icons = page.locator("[data-icon='x-alt']")
    send_icons = page.locator("[data-icon='send']")
    close_visible = any(
        close_icons.nth(index).is_visible() for index in range(close_icons.count())
    )
    send_visible = any(
        send_icons.nth(index).is_visible() for index in range(send_icons.count())
    )
    return close_visible and send_visible and _document_preview_visible(page, names)


def _caption_editor(page: Page, *, allow_footer_editor: bool = False):
    editors = page.locator("div[contenteditable='true']")
    candidates = []
    for index in range(editors.count()):
        editor = editors.nth(index)
        if not editor.is_visible():
            continue
        aria_label = (editor.get_attribute("aria-label") or "").casefold()
        placeholder = " ".join(
            filter(
                None,
                (
                    editor.get_attribute("data-placeholder"),
                    editor.get_attribute("aria-placeholder"),
                    editor.get_attribute("title"),
                ),
            )
        ).casefold()
        description = f"{aria_label} {placeholder}"
        score = 0
        if any(
            term in description
            for term in ("caption", "pie de foto", "comentario", "descripci")
        ):
            score += 100
        if editor.locator("xpath=ancestor::*[@role='dialog']").count():
            score += 20
        in_footer = bool(editor.locator("xpath=ancestor::footer").count())
        if not in_footer and editor.get_attribute("role") == "textbox":
            score += 40
        if in_footer and allow_footer_editor:
            score += 80
        elif in_footer:
            score -= 50
        candidates.append((score, index, editor))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2] if candidates[0][0] > 0 else None


def _same_editor_text(
    actual: str | None,
    expected: str,
    *,
    require_full_match: bool = False,
) -> bool:
    def normalize(value: str) -> str:
        return " ".join(value.replace("\u200b", "").split())

    actual_normalized = normalize(actual or "")
    expected_normalized = normalize(expected)
    if require_full_match:
        return actual_normalized == expected_normalized or (
            len(actual_normalized) >= 80
            and actual_normalized in expected_normalized
            and any(
                marker in actual_normalized
                for marker in (
                    "TikTok",
                    "citaspolarizadasperu",
                    "Gracias por confiar",
                )
            )
        ) or _compact_alphanumeric_text(actual or "") == _compact_alphanumeric_text(
            expected
        )
    return actual_normalized == expected_normalized or len(actual_normalized) >= max(
        20,
        len(expected_normalized) // 2,
    )


def _compact_alphanumeric_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character.casefold()
        for character in decomposed
        if character.isalnum()
    )


def _caption_editor_summary(page: Page) -> list[dict[str, object]]:
    editors = page.locator(
        "[contenteditable='true'], textarea, input, "
        "[aria-placeholder], [aria-label*='caption' i], "
        "[aria-label*='comentario' i], [aria-label*='descripci' i]"
    )
    summary: list[dict[str, object]] = []
    for index in range(min(editors.count(), 12)):
        editor = editors.nth(index)
        if not editor.is_visible():
            continue
        summary.append(
            {
                "aria_label": editor.get_attribute("aria-label"),
                "aria_placeholder": editor.get_attribute("aria-placeholder"),
                "data_placeholder": editor.get_attribute("data-placeholder"),
                "data_tab": editor.get_attribute("data-tab"),
                "title": editor.get_attribute("title"),
                "tag": editor.evaluate("element => element.tagName"),
                "role": editor.get_attribute("role"),
                "contenteditable": editor.get_attribute("contenteditable"),
                "in_dialog": bool(editor.locator("xpath=ancestor::*[@role='dialog']").count()),
                "in_footer": bool(editor.locator("xpath=ancestor::footer").count()),
            }
        )
    return summary


def _safe_get_attribute(locator, name: str) -> str | None:
    try:
        return locator.get_attribute(name, timeout=1_000)
    except PlaywrightError:
        return None


def _safe_text_content(locator) -> str:
    try:
        return locator.text_content(timeout=1_000) or ""
    except PlaywrightError:
        return ""


def _visible(page: Page, selector: str) -> bool:
    locator = page.locator(selector).first
    return bool(locator.count() and locator.is_visible())


def _attachment_control_summary(page: Page) -> list[dict[str, object]]:
    controls = page.locator("button, [role='button'], [data-icon]")
    summary: list[dict[str, object]] = []
    for index in range(min(controls.count(), 80)):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        icons = control.locator("[data-icon]")
        summary.append(
            {
                "tag": control.evaluate("element => element.tagName"),
                "aria_label": _safe_get_attribute(control, "aria-label"),
                "title": _safe_get_attribute(control, "title"),
                "data_testid": _safe_get_attribute(control, "data-testid"),
                "data_icon": _safe_get_attribute(control, "data-icon"),
                "icons": [
                    _safe_get_attribute(icons.nth(icon_index), "data-icon")
                    for icon_index in range(min(icons.count(), 4))
                ],
            }
        )
    return summary
