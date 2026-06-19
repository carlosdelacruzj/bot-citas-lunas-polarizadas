from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import BrowserContext, Page, sync_playwright

from appointment_bot.config import Settings, load_settings
from appointment_bot.flows.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    AppointmentWorkflowUnavailable,
    click_program_action,
    ensure_reservation_captcha_loaded,
    has_available_date_options,
    open_hidden_appointment_panel_for_observer,
    read_appointment_availability,
    select_available_appointment,
    select_available_site_for_observer,
)
from appointment_bot.flows.login import login
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.notifier import send_telegram_document, send_telegram_message
from appointment_bot.services.tiktok_video import find_executable

logger = logging.getLogger(__name__)

DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
VIDEO_PRE_LOGIN_PRIVACY_SCRIPT = """
() => {
    const install = () => {
        if (!document.getElementById("appointment-bot-video-privacy-style")) {
            const style = document.createElement("style");
            style.id = "appointment-bot-video-privacy-style";
            style.textContent = `
                input:not([type="button"]):not([type="submit"]):not([type="reset"]):not([type="image"]),
                textarea {
                    color: transparent !important;
                    text-shadow: 0 0 0 #777 !important;
                    -webkit-text-security: disc !important;
                }
                .appointment-bot-visible-reservation input,
                .appointment-bot-visible-reservation textarea {
                    color: inherit !important;
                    text-shadow: none !important;
                    -webkit-text-security: none !important;
                }
            `;
            document.head.appendChild(style);
        }
        if (!document.getElementById("appointment-bot-video-watermark")) {
            const banner = document.createElement("div");
            banner.id = "appointment-bot-video-watermark";
            banner.textContent = "DIAGNOSTICO / SIN RESERVA";
            banner.style.cssText = [
                "position:fixed",
                "top:16px",
                "right:16px",
                "z-index:2147483647",
                "background:rgba(146,64,14,.94)",
                "color:white",
                "font:700 16px Arial,sans-serif",
                "padding:10px 14px",
                "border-radius:8px",
                "pointer-events:none"
            ].join(";");
            document.body.appendChild(banner);
        }
        if (!document.getElementById("appointment-bot-video-header-mask")) {
            const mask = document.createElement("div");
            mask.id = "appointment-bot-video-header-mask";
            mask.textContent = "usuario oculto";
            mask.style.cssText = [
                "position:fixed",
                "top:54px",
                "left:0",
                "z-index:2147483647",
                "width:370px",
                "height:42px",
                "background:rgba(248,250,252,.98)",
                "color:#334155",
                "font:700 16px Arial,sans-serif",
                "display:flex",
                "align-items:center",
                "padding-left:16px",
                "pointer-events:none"
            ].join(";");
            document.body.appendChild(mask);
        }
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const original = node.nodeValue || "";
            const masked = original.replace(/\\b\\d{8}\\b/g, "***");
            if (masked !== original) node.nodeValue = masked;
        }
    };
    if (!window.__appointmentBotVideoPreLoginPrivacyMask) {
        window.__appointmentBotVideoPreLoginPrivacyMask = true;
        window.setInterval(install, 250);
        document.addEventListener("DOMContentLoaded", install);
    }
    install();
}
"""
VIDEO_PRIVACY_SCRIPT = """
() => {
    const sensitiveParts = [
        "dni", "documento", "nombre", "paterno", "materno",
        "apellido", "usuario", "username", "email", "mail",
        "captcha", "txtimg", "codigo"
    ];
    const captchaParts = ["captcha", "txtimg", "codigo"];
    const isCaptchaControl = element => {
        const key = [
            element.id, element.name, element.placeholder,
            element.getAttribute("aria-label")
        ].join(" ").toLowerCase();
        return captchaParts.some(part => key.includes(part));
    };
    const shouldShowReservationControl = element => {
        if (isCaptchaControl(element)) return false;
        let current = element;
        for (let depth = 0; current && depth < 5; depth += 1) {
            const text = current.innerText || "";
            if (/Reserva Cita( Peritaje)?/i.test(text) && text.length < 1200) {
                current.classList.add("appointment-bot-visible-reservation");
                return true;
            }
            current = current.parentElement;
        }
        return false;
    };
    const showReservationControl = element => {
        element.style.setProperty("color", "inherit", "important");
        element.style.setProperty("text-shadow", "none", "important");
        element.style.setProperty("-webkit-text-security", "none", "important");
    };
    const mask = () => {
        const controls = Array.from(document.querySelectorAll("input, textarea"));
        controls.forEach(element => {
            const key = [
                element.id, element.name, element.placeholder,
                element.getAttribute("aria-label")
            ].join(" ").toLowerCase();
            const type = (element.type || "").toLowerCase();
            const isSensitive = sensitiveParts.some(part => key.includes(part));
            const canContainSecret = ![
                "hidden", "button", "submit", "reset", "image"
            ].includes(type);
            if (shouldShowReservationControl(element)) {
                showReservationControl(element);
                return;
            }
            if (isSensitive && canContainSecret && element.value) {
                element.value = "***";
            }
        });

        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const original = node.nodeValue || "";
            const masked = original.replace(/\\b\\d{8}\\b/g, "***");
            if (masked !== original) node.nodeValue = masked;
        }

        if (!document.getElementById("appointment-bot-video-watermark")) {
            const banner = document.createElement("div");
            banner.id = "appointment-bot-video-watermark";
            banner.textContent = "DIAGNOSTICO / SIN RESERVA";
            banner.style.cssText = [
                "position:fixed",
                "top:16px",
                "right:16px",
                "z-index:2147483647",
                "background:rgba(146,64,14,.94)",
                "color:white",
                "font:700 16px Arial,sans-serif",
                "padding:10px 14px",
                "border-radius:8px",
                "pointer-events:none"
            ].join(";");
            document.body.appendChild(banner);
        }
        if (!document.getElementById("appointment-bot-video-header-mask")) {
            const mask = document.createElement("div");
            mask.id = "appointment-bot-video-header-mask";
            mask.textContent = "usuario oculto";
            mask.style.cssText = [
                "position:fixed",
                "top:54px",
                "left:0",
                "z-index:2147483647",
                "width:370px",
                "height:42px",
                "background:rgba(248,250,252,.98)",
                "color:#334155",
                "font:700 16px Arial,sans-serif",
                "display:flex",
                "align-items:center",
                "padding-left:16px",
                "pointer-events:none"
            ].join(";");
            document.body.appendChild(mask);
        }
    };
    if (!window.__appointmentBotVideoPrivacyMask) {
        window.__appointmentBotVideoPrivacyMask = true;
        window.setInterval(mask, 250);
        document.addEventListener("DOMContentLoaded", mask);
    }
    mask();
}
"""
MOBILE_DEMO_LAYOUT_SCRIPT = """
() => {
    const apply = () => {
        if (!document.getElementById("appointment-bot-mobile-demo-style")) {
            const style = document.createElement("style");
            style.id = "appointment-bot-mobile-demo-style";
            style.textContent = `
                html, body {
                    min-height: 100vh !important;
                    overflow-x: hidden !important;
                }
                body {
                    padding-bottom: 0 !important;
                    background-size: 190px auto !important;
                }
                form,
                .container,
                .content,
                .main,
                [class*="container"],
                [class*="content"] {
                    margin-bottom: 0 !important;
                }
                footer,
                .footer,
                [class*="footer"] {
                    display: none !important;
                }
            `;
            document.head.appendChild(style);
        }

        const modal = Array.from(document.querySelectorAll("div, section, table"))
            .find(element => /Registra tu cita/i.test(element.innerText || ""));
        if (modal) {
            modal.scrollIntoView({block: "center", inline: "center"});
        } else {
            const detail = Array.from(document.querySelectorAll("div, section, table"))
                .find(element => (
                    /Detalle Seguimiento de Trámite|Etapas Trámite/i
                ).test(element.innerText || ""));
            if (detail) detail.scrollIntoView({block: "start", inline: "center"});
        }
    };
    if (!window.__appointmentBotMobileDemoLayout) {
        window.__appointmentBotMobileDemoLayout = true;
        window.setInterval(apply, 300);
        document.addEventListener("DOMContentLoaded", apply);
    }
    apply();
}
"""


def run_video_diagnostic() -> int:
    parser = argparse.ArgumentParser(
        prog="appointment-bot-record-video",
        description="Graba un diagnostico real del observador sin reservar.",
    )
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="Enviar el video por Telegram si no supera el limite configurado.",
    )
    parser.add_argument(
        "--skip-worker-pause",
        action="store_true",
        help="No pausar el worker continuo antes de grabar.",
    )
    parser.add_argument(
        "--mobile-demo",
        action="store_true",
        help="Probar una grabacion vertical con contexto movil, sin reemplazar el flujo normal.",
    )
    args = parser.parse_args()

    settings = replace(load_settings(require_login=True), auto_reserve=False, record_video=True)
    setup_logging(settings)

    worker_paused = False
    video_path: Path | None = None
    final_video_path: Path | None = None
    zoom_video_path: Path | None = None
    result_status = "unknown"
    result_message = "La grabacion no llego a leer disponibilidad."
    try:
        if not args.skip_worker_pause:
            worker_paused = _pause_worker(settings)
        video_path, result_status, result_message = _record_observer_video(
            settings,
            mobile_demo=args.mobile_demo,
        )
        if args.mobile_demo:
            final_video_path = _export_mobile_demo_final_video(settings, video_path)
            zoom_video_path = _export_mobile_demo_zoom_final_video(settings, video_path)
            print(f"Video movil base: {video_path}")
            if final_video_path is not None:
                print(f"Video movil final: {final_video_path}")
            else:
                print("Video movil final: no generado; se conserva el WebM base.")
            if zoom_video_path is not None:
                print(f"Video movil zoom: {zoom_video_path}")
            else:
                print("Video movil zoom: no generado.")
        else:
            print(f"Video guardado: {video_path}")
        print(f"Resultado: {result_status} - {result_message}")
        if args.send_telegram or settings.record_video_send_telegram:
            _send_video(settings, final_video_path or video_path, result_status, result_message)
        return 0
    except Exception as exc:
        logger.exception("Video diagnostic failed")
        if settings.telegram_enabled:
            send_telegram_message(
                settings,
                f"Fallo la grabacion diagnostica del bot.\n\nDetalle: {type(exc).__name__}: {exc}",
            )
        print(f"[ERROR] {exc}".encode("ascii", errors="replace").decode("ascii"))
        return 1
    finally:
        if worker_paused:
            _resume_worker(settings)


def _record_observer_video(
    settings: Settings,
    *,
    mobile_demo: bool = False,
) -> tuple[Path, str, str]:
    try:
        return _record_with_transferred_session(settings, mobile_demo=mobile_demo)
    except AppointmentWorkflowUnavailable as exc:
        logger.warning(
            "Could not reuse the authenticated session for video; retrying with masked login: %s",
            exc,
        )
        return _record_with_masked_login(settings, mobile_demo=mobile_demo)


def _record_with_transferred_session(
    settings: Settings,
    *,
    mobile_demo: bool = False,
) -> tuple[Path, str, str]:
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="appointment-bot-video-") as directory:
        storage_state_path = Path(directory) / "storage-state.json"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            login_context = browser.new_context()
            try:
                login_page = login_context.new_page()
                login(login_page, settings)
                login_context.storage_state(path=str(storage_state_path))
            finally:
                login_context.close()

            video_context = _new_video_context(
                browser,
                settings,
                storage_state_path,
                mobile_demo=mobile_demo,
            )
            page = video_context.new_page()
            video = page.video
            try:
                page.add_init_script(f"({VIDEO_PRIVACY_SCRIPT})()")
                page.goto(
                    settings.target_url,
                    wait_until="domcontentloaded",
                    timeout=settings.login_timeout_seconds * 1_000,
                )
                result_status, result_message = _execute_recorded_observer_flow(
                    page,
                    settings,
                    mobile_demo=mobile_demo,
                )
            except Exception:
                _close_context_and_remove_video(video_context, browser, video)
                raise
            final_path = _close_context_and_save_video(
                video_context,
                browser,
                video,
                settings,
                mobile_demo=mobile_demo,
            )
            return final_path, result_status, result_message


def _record_with_masked_login(
    settings: Settings,
    *,
    mobile_demo: bool = False,
) -> tuple[Path, str, str]:
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        video_context = _new_video_context(browser, settings, mobile_demo=mobile_demo)
        page = video_context.new_page()
        video = page.video
        try:
            page.add_init_script(f"({VIDEO_PRE_LOGIN_PRIVACY_SCRIPT})()")
            page.add_init_script(f"({VIDEO_PRIVACY_SCRIPT})()")
            login(page, settings)
            result_status, result_message = _execute_recorded_observer_flow(
                page,
                settings,
                mobile_demo=mobile_demo,
            )
        except Exception:
            _close_context_and_remove_video(video_context, browser, video)
            raise
        final_path = _close_context_and_save_video(
            video_context,
            browser,
            video,
            settings,
            mobile_demo=mobile_demo,
        )
        return final_path, result_status, result_message


def _execute_recorded_observer_flow(
    page: Page,
    settings: Settings,
    *,
    mobile_demo: bool = False,
) -> tuple[str, str]:
    _apply_video_overlays(page, mobile_demo=mobile_demo)
    page = click_program_action(page)
    _apply_video_overlays(page, mobile_demo=mobile_demo)
    page.wait_for_timeout(1_000)

    page = open_hidden_appointment_panel_for_observer(page)
    _apply_video_overlays(page, mobile_demo=mobile_demo)
    page.wait_for_timeout(1_000)

    page = select_available_site_for_observer(
        page,
        timeout=settings.postback_timeout_seconds * 1_000,
    )
    _apply_video_overlays(page, mobile_demo=mobile_demo)
    result = read_appointment_availability(
        page,
        include_person=False,
        timeout=settings.read_timeout_seconds * 1_000,
    )
    result_status = result.status
    result_message = result.message

    if result.status == "available" or (
        result.status == "partial" and has_available_date_options(page)
    ):
        result = select_available_appointment(
            page,
            allow_hidden=True,
            include_person=False,
            timeout=settings.postback_timeout_seconds * 1_000,
        )
        result_status = result.status
        result_message = result.message
        _wait_for_captcha_if_available(page, settings)
    _apply_video_overlays(page, mobile_demo=mobile_demo)
    page.wait_for_timeout(2_000)
    return result_status, result_message


def _new_video_context(
    browser,
    settings: Settings,
    storage_state_path: Path | None = None,
    *,
    mobile_demo: bool = False,
) -> BrowserContext:
    if mobile_demo:
        options = dict(
            viewport={"width": 1080, "height": 1920},
            record_video_dir=str(settings.videos_dir),
            record_video_size={"width": 1080, "height": 1920},
            device_scale_factor=1,
            is_mobile=True,
            has_touch=True,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
        )
    else:
        options = dict(
            viewport={
                "width": settings.record_video_width,
                "height": settings.record_video_height,
            },
            record_video_dir=str(settings.videos_dir),
            record_video_size={
                "width": settings.record_video_width,
                "height": settings.record_video_height,
            },
            device_scale_factor=settings.screenshot_device_scale_factor,
        )
    if storage_state_path is not None:
        options["storage_state"] = str(storage_state_path)
    return browser.new_context(**options)


def _close_context_and_save_video(
    context: BrowserContext,
    browser,
    video,
    settings: Settings,
    *,
    mobile_demo: bool = False,
) -> Path:
    context.close()
    browser.close()
    if video is None:
        raise RuntimeError("Playwright did not create a video for this page.")
    source_path = Path(video.path())
    final_path = _final_video_path(settings, mobile_demo=mobile_demo)
    source_path.replace(final_path)
    return final_path


def _close_context_and_remove_video(context: BrowserContext, browser, video) -> None:
    context.close()
    browser.close()
    if video is None:
        return
    try:
        Path(video.path()).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove failed diagnostic video artifact")


def _apply_video_privacy_mask(page: Page) -> None:
    page.evaluate(VIDEO_PRIVACY_SCRIPT)


def _apply_video_overlays(page: Page, *, mobile_demo: bool = False) -> None:
    _apply_video_privacy_mask(page)
    if mobile_demo:
        page.evaluate(MOBILE_DEMO_LAYOUT_SCRIPT)


def _wait_for_captcha_if_available(page: Page, settings: Settings) -> None:
    for selector in APPOINTMENT_PANEL_SCREENSHOT_SELECTORS:
        panel = page.locator(selector).first
        if panel.count() == 0:
            continue
        ensure_reservation_captcha_loaded(
            panel,
            timeout=settings.read_timeout_seconds * 1_000,
        )
        return


def _final_video_path(settings: Settings, *, mobile_demo: bool = False) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    kind = "mobile-demo" if mobile_demo else "diagnostic"
    path = settings.videos_dir / f"appointment-bot-{kind}-{stamp}.webm"
    if not path.exists():
        return path
    return settings.videos_dir / f"appointment-bot-{kind}-{stamp}-{uuid4().hex[:8]}.webm"


def _export_mobile_demo_final_video(settings: Settings, source_path: Path) -> Path | None:
    try:
        ffmpeg = find_executable("ffmpeg")
    except FileNotFoundError as exc:
        logger.warning("Could not export final mobile demo video: %s", exc)
        return None

    output_path = _mobile_demo_final_video_path(settings, source_path)
    command = [
        str(ffmpeg),
        "-y",
        "-i",
        str(source_path),
        "-vf",
        "crop=900:1600:90:0,scale=1080:1920,fps=30,format=yuv420p",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warning("Could not export final mobile demo video: %s", exc)
        return None
    return output_path


def _export_mobile_demo_zoom_final_video(settings: Settings, source_path: Path) -> Path | None:
    try:
        ffmpeg = find_executable("ffmpeg")
    except FileNotFoundError as exc:
        logger.warning("Could not export zoomed mobile demo video: %s", exc)
        return None

    output_path = _mobile_demo_zoom_final_video_path(settings, source_path)
    command = [
        str(ffmpeg),
        "-y",
        "-i",
        str(source_path),
        "-filter_complex",
        _mobile_demo_zoom_filter(),
        "-map",
        "[v]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warning("Could not export zoomed mobile demo video: %s", exc)
        return None
    return output_path


def _mobile_demo_zoom_filter() -> str:
    return ";".join(
        [
            "[0:v]trim=start=0:end=2,setpts=PTS-STARTPTS,"
            "crop=900:1600:90:0,scale=1080:1920,fps=30,format=yuv420p,setsar=1[intro]",
            "[0:v]trim=start=2:end=4.5,setpts=PTS-STARTPTS,"
            "crop=740:1110:170:560,scale=1080:1920,fps=30,format=yuv420p,setsar=1[modal]",
            "[0:v]trim=start=4.5,setpts=PTS-STARTPTS,"
            "crop=720:1080:180:620,scale=1080:1920,fps=30,format=yuv420p,setsar=1[button]",
            "[intro][modal][button]concat=n=3:v=1:a=0[v]",
        ]
    )


def _mobile_demo_final_video_path(settings: Settings, source_path: Path) -> Path:
    stem = source_path.stem.replace(
        "appointment-bot-mobile-demo",
        "appointment-bot-mobile-demo-final",
        1,
    )
    path = settings.videos_dir / f"{stem}.mp4"
    if not path.exists():
        return path
    return settings.videos_dir / f"{stem}-{uuid4().hex[:8]}.mp4"


def _mobile_demo_zoom_final_video_path(settings: Settings, source_path: Path) -> Path:
    stem = source_path.stem.replace(
        "appointment-bot-mobile-demo",
        "appointment-bot-mobile-demo-zoom-final",
        1,
    )
    path = settings.videos_dir / f"{stem}.mp4"
    if not path.exists():
        return path
    return settings.videos_dir / f"{stem}-{uuid4().hex[:8]}.mp4"


def _send_video(settings: Settings, video_path: Path, status: str, message: str) -> None:
    delivered = send_telegram_document(
        settings,
        video_path,
        "Video diagnostico real del bot.\n\n"
        "Modo: observador\n"
        "Reserva ejecutada: no\n"
        f"Resultado: {status} - {message}",
    )
    if not delivered:
        send_telegram_message(
            settings,
            "El video diagnostico fue generado pero no se pudo enviar por Telegram.\n\n"
            f"Ruta local: {video_path}",
        )


def _pause_worker(settings: Settings) -> bool:
    try:
        state = _api_request(settings, "POST", "/pause")
        logger.info("Worker pause requested: %s", _safe_worker_state(state))
        return True
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        logger.warning("Could not pause worker before video diagnostic: %s", exc)
        return False


def _resume_worker(settings: Settings) -> None:
    try:
        state = _api_request(settings, "POST", "/resume")
        logger.info("Worker resumed after video diagnostic: %s", _safe_worker_state(state))
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError):
        logger.exception("Could not resume worker after video diagnostic")


def _api_request(settings: Settings, method: str, path: str) -> dict[str, object]:
    host = os.getenv("APPOINTMENT_BOT_API_HOST", "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = os.getenv("APPOINTMENT_BOT_API_PORT", "8765")
    token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(
        f"http://{host}:{port}{path}",
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    return data if isinstance(data, dict) else {}


def _safe_worker_state(state: dict[str, object]) -> dict[str, object]:
    return {
        "phase": state.get("phase"),
        "paused": state.get("paused"),
        "worker_running": state.get("worker_running"),
    }


if __name__ == "__main__":
    raise SystemExit(run_video_diagnostic())
