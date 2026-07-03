from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from appointment_bot.config import load_settings
from appointment_bot.services.notifier import send_telegram_message, send_telegram_photo


DEFAULT_IMAGES = [
    Path("screenshots/diagnostics/captcha-speed-tests/crop-result-20260701.png"),
    Path("screenshots/diagnostics/captcha-speed-tests/crop-result-20260630-fixed.png"),
    Path("screenshots/diagnostics/captcha-speed-tests/crop-panel-20260702.png"),
    Path("screenshots/diagnostics/captcha-speed-tests/crop-captchaaa.png"),
]


@dataclass
class Reply:
    text: str
    update_id: int
    received_at: float


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure manual Telegram response time for captcha-like images."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Seconds to wait for each Telegram reply.",
    )
    parser.add_argument(
        "--image",
        action="append",
        dest="images",
        help="Image path to send. Can be repeated. Defaults to local captcha test crops.",
    )
    args = parser.parse_args()

    settings = load_settings()
    if not settings.telegram_enabled:
        raise RuntimeError("Telegram is disabled in .env.")

    images = [Path(item) for item in args.images] if args.images else DEFAULT_IMAGES
    missing = [image for image in images if not image.exists()]
    if missing:
        raise FileNotFoundError(f"Missing benchmark image(s): {missing}")

    logs_dir = settings.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    result_path = logs_dir / f"manual-captcha-benchmark-{run_id}.csv"

    offset = _latest_update_offset(settings.telegram_bot_token)
    send_telegram_message(
        settings,
        (
            "Prueba de velocidad manual iniciada.\n\n"
            "Te enviare imagenes una por una. Responde solo el texto que ves. "
            f"Tiempo limite por imagen: {args.timeout}s."
        ),
    )

    rows: list[dict[str, object]] = []
    for index, image in enumerate(images, start=1):
        caption = (
            f"Prueba CAPTCHA {index}/{len(images)}\n"
            "Responde solo el texto que ves en esta imagen."
        )
        sent_at = time.perf_counter()
        delivered = send_telegram_photo(settings, image, caption)
        if not delivered:
            delivered = send_telegram_message(settings, f"{caption}\n\nImagen: {image}")
        if not delivered:
            rows.append(
                {
                    "index": index,
                    "image": str(image),
                    "status": "send_failed",
                    "elapsed_seconds": "",
                    "reply": "",
                    "update_id": "",
                }
            )
            continue

        reply = _wait_for_reply(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            offset,
            timeout_seconds=args.timeout,
        )
        if reply is None:
            rows.append(
                {
                    "index": index,
                    "image": str(image),
                    "status": "timeout",
                    "elapsed_seconds": "",
                    "reply": "",
                    "update_id": "",
                }
            )
            send_telegram_message(settings, f"Prueba {index}: sin respuesta en {args.timeout}s.")
            continue

        offset = reply.update_id + 1
        elapsed = reply.received_at - sent_at
        rows.append(
            {
                "index": index,
                "image": str(image),
                "status": "ok",
                "elapsed_seconds": f"{elapsed:.3f}",
                "reply": reply.text,
                "update_id": reply.update_id,
            }
        )
        send_telegram_message(settings, f"Prueba {index}: recibido en {elapsed:.3f}s.")

    _write_results(result_path, rows)
    summary = _summary(rows)
    send_telegram_message(settings, f"Prueba terminada.\n\n{summary}\n\nLog: {result_path}")
    print(summary)
    print(f"results={result_path}")
    return 0


def _latest_update_offset(token: str) -> int | None:
    data = _telegram_get(token, "getUpdates", {"timeout": "1"})
    updates = data.get("result") or []
    if not updates:
        return None
    return int(max(item.get("update_id", 0) for item in updates)) + 1


def _wait_for_reply(
    token: str,
    chat_id: str,
    offset: int | None,
    *,
    timeout_seconds: int,
) -> Reply | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        remaining = max(1, min(10, int(deadline - time.monotonic())))
        params = {"timeout": str(remaining), "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            params["offset"] = str(offset)
        data = _telegram_get(token, "getUpdates", params)
        for item in data.get("result") or []:
            update_id = int(item.get("update_id", 0))
            message = item.get("message") or {}
            chat = message.get("chat") or {}
            if str(chat.get("id")) != str(chat_id):
                offset = update_id + 1
                continue
            text = str(message.get("text") or "").strip()
            if not text:
                offset = update_id + 1
                continue
            return Reply(text=text, update_id=update_id, received_at=time.perf_counter())
    return None


def _telegram_get(token: str, method: str, params: dict[str, str]) -> dict[str, object]:
    url = f"https://api.telegram.org/bot{token}/{method}?{urlencode(params)}"
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Telegram {method} failed: {exc}") from exc
    data = json.loads(body)
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} rejected request: {data}")
    return data


def _write_results(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = ["index", "image", "status", "elapsed_seconds", "reply", "update_id"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _summary(rows: list[dict[str, object]]) -> str:
    elapsed = [
        float(row["elapsed_seconds"])
        for row in rows
        if row.get("status") == "ok" and row.get("elapsed_seconds")
    ]
    if not elapsed:
        return "No hubo respuestas medidas."
    return (
        "Resumen manual:\n"
        f"Respuestas: {len(elapsed)}/{len(rows)}\n"
        f"Promedio: {sum(elapsed) / len(elapsed):.3f}s\n"
        f"Minimo: {min(elapsed):.3f}s\n"
        f"Maximo: {max(elapsed):.3f}s"
    )


if __name__ == "__main__":
    raise SystemExit(main())
