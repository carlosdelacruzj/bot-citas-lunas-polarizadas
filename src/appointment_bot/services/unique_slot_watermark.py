from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import date
from pathlib import Path
from queue import Queue
from uuid import uuid4

from PIL import Image, PngImagePlugin

from appointment_bot.config import Settings
from appointment_bot.utils.screenshots import screenshot_artifact_dir_for_date

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(".runtime/whatsapp-daily-summary/config.json")
LAYOUT_VERSION = "provided-assets-v8-channel-pattern-1"
ORIGINAL_DIRECTORY_NAME = "cupos-unicos"
WATERMARKED_DIRECTORY_NAME = "cupos-unicos-marcados"
BRAND_ASSETS_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "brand"
CENTRAL_WATERMARK_PATH = BRAND_ASSETS_DIRECTORY / "Logo transparente.png"
BOTTOM_SIGNATURE_PATH = BRAND_ASSETS_DIRECTORY / "logo con numero.png"
CHANNEL_SIGNATURE_PATH = BRAND_ASSETS_DIRECTORY / "Nombre canal.png"
BRAND_NAME = "Citas Lunas Polarizadas"
BOTTOM_SIGNATURE_PHONE = "925 761 698"

_watermark_queue: Queue[tuple[Settings, Path]] = Queue()
_watermark_lock = threading.Lock()
_watermark_pending: set[str] = set()
_watermark_thread: threading.Thread | None = None
_asset_lock = threading.Lock()
_asset_cache: dict[Path, Image.Image] = {}


def queue_unique_slot_watermark(settings: Settings, source: Path) -> None:
    """Queue best-effort rendering without delaying CAPTCHA or reservation work."""
    source = source.resolve()
    destination = watermarked_slot_path(source)
    if _watermark_is_current(source, destination, _configured_public_whatsapp()):
        return

    source_key = str(source).casefold()
    with _watermark_lock:
        if source_key in _watermark_pending:
            return
        _watermark_pending.add(source_key)
        _ensure_watermark_worker_locked()
    _watermark_queue.put((settings, source))


def prepare_daily_unique_slot_watermarks(
    settings: Settings,
    report_date: date,
    *,
    public_whatsapp: str,
) -> list[Path]:
    """Synchronously reconcile every branded derivative before daily enqueue."""
    source_directory = screenshot_artifact_dir_for_date(
        settings,
        report_date,
        ORIGINAL_DIRECTORY_NAME,
    )
    if not source_directory.is_dir():
        return []

    sources = sorted(
        (path.resolve() for path in source_directory.glob("*.png") if path.is_file()),
        key=lambda path: path.name,
    )
    rendered: list[Path] = []
    failures: list[str] = []
    for source in sources:
        try:
            rendered.append(
                ensure_unique_slot_watermark(
                    settings,
                    source,
                    public_whatsapp=public_whatsapp,
                )
            )
        except Exception as exc:
            logger.exception("Could not prepare branded slot image: %s", source)
            failures.append(f"{source.name}: {exc}")

    if failures:
        raise RuntimeError(
            "No se pudo preparar el resumen sin exponer imagenes originales: "
            + "; ".join(failures)
        )
    return rendered


def ensure_unique_slot_watermark(
    settings: Settings,
    source: Path,
    *,
    public_whatsapp: str,
) -> Path:
    del settings  # Reserved for future project-local layout configuration.
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"No existe la captura original: {source}")
    phone_display = _public_whatsapp_display(public_whatsapp)
    if phone_display != BOTTOM_SIGNATURE_PHONE:
        raise ValueError(
            "El WhatsApp configurado no coincide con el numero incrustado en "
            f"{BOTTOM_SIGNATURE_PATH.name}."
        )
    destination = watermarked_slot_path(source)
    fingerprint = _watermark_fingerprint(source, phone_display)
    if _watermark_is_current(
        source,
        destination,
        phone_display,
        expected_fingerprint=fingerprint,
    ):
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.stem}.{uuid4().hex}.tmp{destination.suffix}"
    )
    try:
        _render_watermark(source, temporary, fingerprint)
        _verify_rendered_image(source, temporary, fingerprint)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    logger.info("Prepared branded unique slot image: %s", destination)
    return destination


def watermarked_slot_path(source: Path) -> Path:
    if source.parent.name != ORIGINAL_DIRECTORY_NAME:
        raise ValueError(
            f"La captura no pertenece a {ORIGINAL_DIRECTORY_NAME}: {source}"
        )
    return source.parent.parent / WATERMARKED_DIRECTORY_NAME / source.name


def validate_daily_watermarked_attachment_paths(
    settings: Settings,
    report_date: date,
    attachment_paths: list[str],
) -> list[str]:
    expected_directory = screenshot_artifact_dir_for_date(
        settings,
        report_date,
        WATERMARKED_DIRECTORY_NAME,
    ).resolve()
    validated: list[str] = []
    for raw_path in attachment_paths:
        path = Path(raw_path).resolve()
        if path.parent != expected_directory:
            raise ValueError(
                "El resumen diario contiene una imagen fuera de cupos-unicos-marcados."
            )
        if not path.is_file():
            raise FileNotFoundError(f"No existe la imagen marcada del resumen: {path}")
        with Image.open(path) as image:
            if image.info.get("watermark_layout") != LAYOUT_VERSION:
                raise ValueError(f"La imagen no contiene la marca vigente: {path}")
            image.verify()
        validated.append(str(path))
    return validated


def _ensure_watermark_worker_locked() -> None:
    global _watermark_thread
    if _watermark_thread is not None and _watermark_thread.is_alive():
        return
    _watermark_thread = threading.Thread(
        target=_watermark_worker,
        name="unique-slot-watermark",
        daemon=True,
    )
    _watermark_thread.start()


def _watermark_worker() -> None:
    while True:
        settings, source = _watermark_queue.get()
        source_key = str(source).casefold()
        try:
            public_whatsapp = _configured_public_whatsapp()
            if public_whatsapp is None:
                logger.warning(
                    "Unique slot watermark skipped because public_whatsapp is not configured"
                )
                continue
            ensure_unique_slot_watermark(
                settings,
                source,
                public_whatsapp=public_whatsapp,
            )
        except Exception:
            logger.exception("Could not prepare unique slot watermark: %s", source)
        finally:
            with _watermark_lock:
                _watermark_pending.discard(source_key)
            _watermark_queue.task_done()


def _configured_public_whatsapp() -> str | None:
    if not CONFIG_PATH.is_file():
        return None
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        logger.exception("Could not read the daily summary watermark configuration")
        return None
    if not isinstance(payload, dict) or payload.get("enabled") is False:
        return None
    value = str(payload.get("public_whatsapp") or "").strip()
    return value or None


def _public_whatsapp_display(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 11 and digits.startswith("51"):
        digits = digits[2:]
    if len(digits) != 9:
        raise ValueError("public_whatsapp debe contener un numero peruano de 9 digitos.")
    return " ".join(digits[index : index + 3] for index in range(0, 9, 3))


def _watermark_fingerprint(source: Path, phone_display: str) -> str:
    digest = hashlib.sha256()
    digest.update(LAYOUT_VERSION.encode("utf-8"))
    digest.update(phone_display.encode("utf-8"))
    for path in (
        source,
        CENTRAL_WATERMARK_PATH,
        BOTTOM_SIGNATURE_PATH,
        CHANNEL_SIGNATURE_PATH,
    ):
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _watermark_is_current(
    source: Path,
    destination: Path,
    public_whatsapp: str | None,
    *,
    expected_fingerprint: str | None = None,
) -> bool:
    if public_whatsapp is None or not source.is_file() or not destination.is_file():
        return False
    try:
        phone_display = _public_whatsapp_display(public_whatsapp)
        fingerprint = expected_fingerprint or _watermark_fingerprint(source, phone_display)
        _verify_rendered_image(source, destination, fingerprint)
    except (OSError, TypeError, ValueError):
        return False
    return True


def _verify_rendered_image(source: Path, destination: Path, fingerprint: str) -> None:
    with Image.open(source) as original, Image.open(destination) as rendered:
        if rendered.size != original.size:
            raise ValueError("La imagen marcada no conserva las dimensiones originales.")
        if rendered.info.get("watermark_fingerprint") != fingerprint:
            raise ValueError("La imagen marcada no corresponde al original o al diseno vigente.")
        rendered.verify()


def _render_watermark(
    source: Path,
    destination: Path,
    fingerprint: str,
) -> None:
    with Image.open(source) as original:
        canvas = original.convert("RGBA")

    width, height = canvas.size
    central_watermark = _get_brand_asset(CENTRAL_WATERMARK_PATH)
    bottom_signature = _get_brand_asset(BOTTOM_SIGNATURE_PATH)
    channel_signature = _get_brand_asset(CHANNEL_SIGNATURE_PATH)
    _paste_center_watermark(canvas, central_watermark)
    _paste_channel_signature(canvas, channel_signature)
    _paste_horizontal_channel_names(canvas, channel_signature)
    _paste_bottom_signature(canvas, bottom_signature)

    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("watermark_layout", LAYOUT_VERSION)
    metadata.add_text("watermark_fingerprint", fingerprint)
    metadata.add_text("watermark_owner", BRAND_NAME)
    canvas.convert("RGB").save(destination, format="PNG", pnginfo=metadata, optimize=True)


def _get_brand_asset(path: Path) -> Image.Image:
    with _asset_lock:
        cached = _asset_cache.get(path)
        if cached is not None:
            return cached.copy()
        if not path.is_file():
            raise FileNotFoundError(f"No existe el recurso de marca: {path}")
        with Image.open(path) as source:
            asset = source.convert("RGBA")
        bounds = asset.getchannel("A").getbbox()
        if bounds is None:
            raise ValueError(f"El recurso de marca no contiene pixeles visibles: {path}")
        _asset_cache[path] = asset.crop(bounds)
        return _asset_cache[path].copy()


def _paste_center_watermark(canvas: Image.Image, watermark: Image.Image) -> None:
    width, height = canvas.size
    maximum_width = max(1, round(width * 0.44))
    maximum_height = max(1, round(height * 0.405))
    watermark.thumbnail((maximum_width, maximum_height), Image.Resampling.LANCZOS)
    opacity = watermark.getchannel("A").point(lambda value: round(value * 0.20))
    watermark.putalpha(opacity)
    x = (width - watermark.width) // 2
    y = max(0, round(height * 0.51 - watermark.height / 2))
    canvas.alpha_composite(watermark, (x, y))


def _paste_bottom_signature(canvas: Image.Image, signature: Image.Image) -> None:
    width, height = canvas.size
    maximum_width = max(1, round(width * 0.52))
    maximum_height = max(1, round(height * 0.102))
    signature.thumbnail((maximum_width, maximum_height), Image.Resampling.LANCZOS)
    x = round(width * 0.025)
    footer_top = round(height * 0.756)
    footer_bottom = round(height * 0.857)
    y = footer_top + (footer_bottom - footer_top - signature.height) // 2
    canvas.alpha_composite(signature, (x, max(0, y)))


def _paste_channel_signature(canvas: Image.Image, signature: Image.Image) -> None:
    width, height = canvas.size
    maximum_width = max(1, round(width * 0.20))
    maximum_height = max(1, round(height * 0.058))
    signature.thumbnail((maximum_width, maximum_height), Image.Resampling.LANCZOS)
    opacity = signature.getchannel("A").point(lambda value: round(value * 0.82))
    signature.putalpha(opacity)
    x = width - signature.width - round(width * 0.025)
    header_top = round(height * 0.14)
    header_bottom = round(height * 0.224)
    y = header_top + (header_bottom - header_top - signature.height) // 2
    canvas.alpha_composite(signature, (max(0, x), max(0, y)))


def _paste_horizontal_channel_names(
    canvas: Image.Image,
    channel_signature: Image.Image,
) -> None:
    width, height = canvas.size
    channel_name = _channel_name_from_signature(channel_signature)
    maximum_width = max(1, round(width * 0.19))
    maximum_height = max(1, round(height * 0.025))
    channel_name.thumbnail((maximum_width, maximum_height), Image.Resampling.LANCZOS)
    opacity = channel_name.getchannel("A").point(lambda value: round(value * 0.15))
    channel_name.putalpha(opacity)

    side_margin = round(width * 0.045)
    middle_y = round(height * 0.47)
    positions = (
        (side_margin, middle_y),
        (width - side_margin - channel_name.width, middle_y),
        ((width - channel_name.width) // 2, round(height * 0.706)),
    )
    for x, y in positions:
        canvas.alpha_composite(channel_name, (max(0, x), max(0, y)))


def _channel_name_from_signature(signature: Image.Image) -> Image.Image:
    """Extract the supplied white username without recreating its typography."""
    username_region = signature.crop(
        (round(signature.width * 0.24), 0, signature.width, signature.height)
    )
    red, green, blue, alpha = username_region.split()
    white_mask = Image.new("L", username_region.size)
    white_mask.putdata(
        [
            source_alpha
            if min(red_value, green_value, blue_value) >= 175
            else 0
            for red_value, green_value, blue_value, source_alpha in zip(
                red.get_flattened_data(),
                green.get_flattened_data(),
                blue.get_flattened_data(),
                alpha.get_flattened_data(),
                strict=True,
            )
        ]
    )
    bounds = white_mask.getbbox()
    if bounds is None:
        raise ValueError(
            f"El recurso de marca no contiene el nombre visible: {CHANNEL_SIGNATURE_PATH}"
        )
    username = Image.new("RGBA", username_region.size, (39, 55, 72, 0))
    username.putalpha(white_mask)
    return username.crop(bounds)


__all__ = [
    "ensure_unique_slot_watermark",
    "prepare_daily_unique_slot_watermarks",
    "queue_unique_slot_watermark",
    "validate_daily_watermarked_attachment_paths",
    "watermarked_slot_path",
]
