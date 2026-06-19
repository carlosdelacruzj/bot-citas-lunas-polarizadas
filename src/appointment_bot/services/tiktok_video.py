from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("videos") / "tiktok"
DEFAULT_MIN_SECONDS = 24
DEFAULT_MAX_SECONDS = 35
DEFAULT_STYLE = "scenes"


def run_tiktok_video() -> int:
    parser = argparse.ArgumentParser(
        prog="appointment-bot-tiktok-video",
        description="Exporta una demo vertical MP4 para TikTok desde un video diagnostico.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Video diagnostico de entrada. Si se omite, usa el ultimo .webm en videos/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ruta MP4 de salida. Si se omite, genera una en videos/tiktok/.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_MIN_SECONDS,
        help="Duracion objetivo en segundos cuando el video de entrada es corto.",
    )
    parser.add_argument(
        "--style",
        choices=("scenes", "full-frame"),
        default=DEFAULT_STYLE,
        help="Estilo de exportacion. 'scenes' usa zoom por escenas.",
    )
    parser.add_argument(
        "--stages-image",
        type=Path,
        default=None,
        help="Captura sanitizada de etapas. Si se omite, usa la ultima disponible.",
    )
    parser.add_argument(
        "--panel-image",
        type=Path,
        default=None,
        help="Captura sanitizada del panel de citas. Si se omite, usa la ultima disponible.",
    )
    args = parser.parse_args()

    try:
        input_path = args.input or latest_diagnostic_video(Path("videos"))
        output_path = args.output or default_output_path(DEFAULT_OUTPUT_DIR)
        export_tiktok_video(
            input_path=input_path,
            output_path=output_path,
            target_duration_seconds=args.duration,
            style=args.style,
            stages_image=args.stages_image,
            panel_image=args.panel_image,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}".encode("ascii", errors="replace").decode("ascii"))
        return 1

    print(f"Video TikTok generado: {output_path}")
    return 0


def latest_diagnostic_video(videos_dir: Path) -> Path:
    candidates = sorted(
        videos_dir.glob("appointment-bot-diagnostic-*.webm"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No diagnostic .webm videos were found in videos/.")
    return candidates[0]


def default_output_path(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output_dir / f"appointment-bot-tiktok-{stamp}.mp4"


def export_tiktok_video(
    *,
    input_path: Path,
    output_path: Path,
    target_duration_seconds: int = DEFAULT_MIN_SECONDS,
    style: str = DEFAULT_STYLE,
    stages_image: Path | None = None,
    panel_image: Path | None = None,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(f"Input video does not exist: {input_path}")

    ffmpeg = find_executable("ffmpeg")
    if style == "scenes":
        export_scenes_video(
            ffmpeg=ffmpeg,
            output_path=output_path,
            stages_image=stages_image or latest_screenshot(("real-test-corrected-01-*.png",)),
            panel_image=panel_image
            or latest_screenshot(
                (
                    "real-test-corrected-03-*.png",
                    "real-test-04-no-slots-panel-*.png",
                )
            ),
        )
        return

    ffprobe = find_executable("ffprobe")
    duration = probe_duration(ffprobe, input_path)
    export_seconds = _export_duration(duration, target_duration_seconds)
    loop_args = ["-stream_loop", "-1"] if duration < target_duration_seconds else []

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg),
        "-y",
        *loop_args,
        "-i",
        str(input_path),
        "-t",
        str(export_seconds),
        "-vf",
        _full_frame_filter(),
        "-r",
        "30",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def latest_screenshot(
    patterns: tuple[str, ...], screenshots_dir: Path = Path("screenshots")
) -> Path:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(screenshots_dir.rglob(pattern))
    candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        joined = ", ".join(patterns)
        raise FileNotFoundError(f"No screenshots found for patterns: {joined}")
    return candidates[0]


def export_scenes_video(
    *,
    ffmpeg: Path,
    output_path: Path,
    stages_image: Path,
    panel_image: Path,
) -> None:
    if not stages_image.exists():
        raise FileNotFoundError(f"Stages image does not exist: {stages_image}")
    if not panel_image.exists():
        raise FileNotFoundError(f"Panel image does not exist: {panel_image}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg),
        "-y",
        "-loop",
        "1",
        "-t",
        "20",
        "-i",
        str(stages_image),
        "-loop",
        "1",
        "-t",
        "20",
        "-i",
        str(panel_image),
        "-filter_complex",
        _image_scenes_filter(),
        "-map",
        "[v]",
        "-r",
        "30",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def find_executable(name: str) -> Path:
    configured = os.getenv(f"{name.upper()}_PATH", "").strip()
    if configured:
        path = Path(configured)
        if path.exists():
            return path

    found = shutil.which(name)
    if found:
        return Path(found)

    winget_root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for path in winget_root.glob(f"**/{name}.exe"):
        return path

    raise FileNotFoundError(f"{name} was not found. Install ffmpeg and reopen the terminal.")


def probe_duration(ffprobe: Path, input_path: Path) -> float:
    result = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return max(0.1, float(result.stdout.strip()))
    except ValueError as exc:
        raise RuntimeError(f"Could not read video duration for {input_path}") from exc


def _export_duration(source_duration: float, target_duration_seconds: int) -> int:
    if source_duration < target_duration_seconds:
        return max(1, target_duration_seconds)
    return min(DEFAULT_MAX_SECONDS, max(1, int(source_duration)))


def _image_scenes_filter() -> str:
    font = _font_file()
    filters = [
        "[0:v]scale=980:1000:force_original_aspect_ratio=decrease,"
        "pad=980:1000:(ow-iw)/2:(oh-ih)/2:color=0xf8fafc,setsar=1[stagesimg]",
        "[1:v]split=2[panelsrc1][panelsrc2];"
        "[panelsrc1]scale=980:620:force_original_aspect_ratio=decrease,"
        "pad=980:620:(ow-iw)/2:(oh-ih)/2:color=0xf8fafc,setsar=1[panelimg]",
        "[panelsrc2]scale=1020:760:force_original_aspect_ratio=decrease,"
        "pad=1020:760:(ow-iw)/2:(oh-ih)/2:color=0xf8fafc,setsar=1[resultimg]",
        _static_title_scene(
            "cover", 4, "Bot monitoreando citas", "Demo segura / sin reserva", font
        ),
        _static_image_scene(
            "stages",
            "stagesimg",
            5,
            "Lee el estado del tramite",
            "Avance sin datos personales",
            50,
            430,
            font,
        ),
        _static_image_scene(
            "panel",
            "panelimg",
            5,
            "Revisa disponibilidad",
            "Sede, fecha, hora y cupos",
            50,
            600,
            font,
        ),
        _static_image_scene(
            "result", "resultimg", 5, "Detecta cupos", "Disponible o Sin Cupos", 30, 560, font
        ),
        _static_title_scene(
            "close", 5, "Modo observador", "No reserva y no muestra datos reales", font
        ),
        "[cover][stages][panel][result][close]concat=n=5:v=1:a=0[v]",
    ]
    return ";".join(filters)


def _static_title_scene(label: str, duration: int, title: str, subtitle: str, font: str) -> str:
    return (
        f"color=c=0x0f172a:s=1080x1920:d={duration},"
        "drawbox=x=0:y=0:w=1080:h=1920:color=black@0.10:t=fill,"
        f"drawtext=fontfile='{font}':text='{title}':"
        "x=70:y=700:fontsize=68:fontcolor=white,"
        f"drawtext=fontfile='{font}':text='{subtitle}':"
        "x=70:y=800:fontsize=40:fontcolor=0x99f6e4,"
        f"drawtext=fontfile='{font}':text='Video demo':"
        "x=70:y=1700:fontsize=34:fontcolor=0xe2e8f0,"
        f"drawtext=fontfile='{font}':text='Sin datos personales visibles':"
        f"x=70:y=1760:fontsize=34:fontcolor=0xe2e8f0,"
        f"trim=duration={duration},setpts=PTS-STARTPTS,"
        f"fps=30,format=yuv420p,setsar=1[{label}]"
    )


def _static_image_scene(
    label: str,
    image_label: str,
    duration: int,
    title: str,
    subtitle: str,
    x: int,
    y: int,
    font: str,
) -> str:
    return (
        f"color=c=0x0f172a:s=1080x1920:d={duration},"
        "drawbox=x=0:y=0:w=1080:h=350:color=black@0.24:t=fill,"
        "drawbox=x=0:y=1510:w=1080:h=410:color=black@0.38:t=fill,"
        f"drawtext=fontfile='{font}':text='{title}':"
        "x=60:y=90:fontsize=58:fontcolor=white,"
        f"drawtext=fontfile='{font}':text='{subtitle}':"
        "x=60:y=172:fontsize=34:fontcolor=0x99f6e4,"
        f"drawtext=fontfile='{font}':text='Demo segura / sin datos personales':"
        f"x=60:y=1645:fontsize=34:fontcolor=white[base_{label}];"
        f"[base_{label}][{image_label}]overlay={x}:{y}:shortest=1,"
        "drawbox=x=50:y=430:w=390:h=90:color=0xf8fafc@1.0:t=fill,"
        "drawbox=x=50:y=430:w=390:h=90:color=0x0f172a@0.08:t=fill,"
        f"drawtext=fontfile='{font}':text='zona privada oculta':"
        "x=70:y=462:fontsize=24:fontcolor=0x334155,"
        f"drawbox=x={x}:y={y}:w=980:h=1000:color=white@0.12:t=8,"
        f"trim=duration={duration},setpts=PTS-STARTPTS,"
        f"fps=30,format=yuv420p,setsar=1[{label}]"
    )


def _full_frame_filter() -> str:
    font = _font_file()
    return (
        "[0:v]split=2[bgsrc][fgsrc];"
        "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=24:1,eq=brightness=-0.12:saturation=0.75[bg];"
        "[fgsrc]scale=1000:650:force_original_aspect_ratio=decrease,"
        "pad=1000:650:(ow-iw)/2:(oh-ih)/2:color=0x0f172a[fg];"
        "[bg]drawbox=x=0:y=0:w=1080:h=410:color=black@0.66:t=fill,"
        "drawbox=x=0:y=1580:w=1080:h=340:color=black@0.62:t=fill[top];"
        "[top][fg]overlay=40:560,"
        f"drawtext=fontfile='{font}':text='Bot monitoreando citas':"
        "x=60:y=90:fontsize=58:fontcolor=white,"
        f"drawtext=fontfile='{font}':text='Demo segura / sin reserva':"
        "x=60:y=170:fontsize=36:fontcolor=0x99f6e4,"
        f"drawtext=fontfile='{font}':text='Revision automatica del portal':"
        "x=60:y=1625:fontsize=38:fontcolor=white,"
        f"drawtext=fontfile='{font}':text='Detecta estado actual - Sin Cupos o Disponible':"
        "x=60:y=1690:fontsize=34:fontcolor=0xe2e8f0,"
        f"drawtext=fontfile='{font}':text='Sin datos personales visibles':"
        "x=60:y=1750:fontsize=34:fontcolor=0xe2e8f0,"
        "drawbox=x=40:y=630:w=360:h=44:color=white@1.0:t=fill,"
        "drawbox=x=40:y=630:w=360:h=44:color=0x0f172a@0.10:t=fill,"
        f"drawtext=fontfile='{font}':text='usuario oculto':"
        "x=56:y=640:fontsize=22:fontcolor=0x334155,"
        "drawbox=x=40:y=520:w=1000:h=700:color=white@0.10:t=8"
    )


def _font_file() -> str:
    candidates = [
        Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf",
    ]
    for path in candidates:
        if path.exists():
            return str(path).replace("\\", "/").replace(":", "\\:")
    raise FileNotFoundError("Could not find a Windows font for ffmpeg drawtext.")


if __name__ == "__main__":
    raise SystemExit(run_tiktok_video())
