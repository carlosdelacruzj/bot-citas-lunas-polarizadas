from __future__ import annotations

import csv
import hashlib
import io
import math
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any

ALLOWED_CASE_TYPES = {
    "wrong",
    "high_confidence_wrong",
    "unanimous_wrong",
    "majority_wrong",
    "disagreement",
}
HIGH_CONFIDENCE_THRESHOLD = 0.9


def build_captcha_quality(
    events: list[dict[str, Any]],
    external_solver_ms: dict[str, float | int | None],
) -> dict[str, Any]:
    canonical = _canonical_events(events)
    validated = [event for event in canonical if _human_answer(event)]
    predictions_by_model: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = (
        defaultdict(list)
    )
    for event in canonical:
        for prediction in _predictions(event):
            model_name = str(prediction.get("model_name") or "").strip()
            if model_name:
                predictions_by_model[model_name].append((event, prediction))

    models = []
    for model_name in sorted(predictions_by_model):
        pairs = predictions_by_model[model_name]
        evaluated = [
            (event, prediction)
            for event, prediction in pairs
            if _human_answer(event)
        ]
        correct = [
            prediction
            for event, prediction in evaluated
            if _prediction_answer(prediction) == _human_answer(event)
        ]
        wrong = [
            prediction
            for event, prediction in evaluated
            if _prediction_answer(prediction) != _human_answer(event)
        ]
        inference_values = _numeric_values(
            prediction.get("inference_ms") for _, prediction in pairs
        )
        confidence_values = _numeric_values(
            prediction.get("mean_confidence") for _, prediction in pairs
        )
        models.append(
            {
                "model_name": model_name,
                "predictions": len(pairs),
                "evaluated": len(evaluated),
                "correct": len(correct),
                "accuracy": _ratio(len(correct), len(evaluated)),
                "confidence": {
                    "average": _average(confidence_values),
                    "correct_average": _average(
                        _numeric_values(item.get("mean_confidence") for item in correct)
                    ),
                    "wrong_average": _average(
                        _numeric_values(item.get("mean_confidence") for item in wrong)
                    ),
                },
                "inference_ms": _distribution(inference_values),
            }
        )

    cases = build_captcha_quality_cases(canonical)
    local_total_values = []
    for event in canonical:
        timings = _numeric_values(
            prediction.get("inference_ms") for prediction in _predictions(event)
        )
        if timings:
            local_total_values.append(sum(timings))
    ensemble = {
        "unanimous": sum("unanimous" in case["agreement_types"] for case in cases),
        "unanimous_validated": sum(
            "unanimous" in case["agreement_types"] and bool(case["human_answer"])
            for case in cases
        ),
        "unanimous_wrong": sum(
            "unanimous_wrong" in case["case_types"] for case in cases
        ),
        "majority": sum("majority" in case["agreement_types"] for case in cases),
        "majority_wrong": sum("majority_wrong" in case["case_types"] for case in cases),
        "all_different": sum(
            "all_different" in case["agreement_types"] for case in cases
        ),
    }
    weekly = _weekly_quality(validated)
    return {
        "events": len(canonical),
        "validated_images": len(validated),
        "weeks_observed": len(weekly),
        "trend_ready": len(weekly) >= 2 and len(validated) >= 30,
        "models": models,
        "ensemble": ensemble,
        "weekly": weekly,
        "useful_case_counts": {
            case_type: sum(case_type in case["case_types"] for case in cases)
            for case_type in sorted(ALLOWED_CASE_TYPES)
        },
        "local_total_ms": _distribution(local_total_values),
        "external_solver_ms": external_solver_ms,
        "definitions": {
            "accuracy_reference": "latest_human_label_by_image_sha256",
            "percentile_method": "linear_interpolation",
            "high_confidence_threshold": HIGH_CONFIDENCE_THRESHOLD,
        },
    }


def build_captcha_quality_cases(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for event in _canonical_events(events):
        human_answer = _human_answer(event)
        predictions = _predictions(event)
        if not human_answer or not predictions:
            continue
        counts = Counter(_prediction_answer(item) for item in predictions)
        counts.pop("", None)
        if not counts:
            continue
        leading_answer, vote_count = counts.most_common(1)[0]
        unanimous = len(counts) == 1
        majority = not unanimous and vote_count > len(predictions) / 2
        all_different = len(counts) == len(predictions) and len(predictions) > 1
        wrong_models = [
            str(item.get("model_name") or "")
            for item in predictions
            if _prediction_answer(item) != human_answer
        ]
        high_confidence_wrong_models = [
            str(item.get("model_name") or "")
            for item in predictions
            if _prediction_answer(item) != human_answer
            and (_as_float(item.get("mean_confidence")) or 0)
            >= HIGH_CONFIDENCE_THRESHOLD
        ]
        case_types: list[str] = []
        agreement_types: list[str] = []
        if unanimous:
            agreement_types.append("unanimous")
        elif majority:
            agreement_types.append("majority")
        elif all_different:
            agreement_types.append("all_different")
        if len(counts) > 1:
            case_types.append("disagreement")
        if wrong_models:
            case_types.append("wrong")
        if high_confidence_wrong_models:
            case_types.append("high_confidence_wrong")
        if unanimous and leading_answer != human_answer:
            case_types.append("unanimous_wrong")
        if majority and leading_answer != human_answer:
            case_types.append("majority_wrong")
        cases.append(
            {
                "event_id": str(event.get("event_id") or ""),
                "image_sha256": str(event.get("image_sha256") or ""),
                "received_at_utc": event.get("received_at_utc"),
                "human_answer": human_answer,
                "case_types": case_types,
                "agreement_types": agreement_types,
                "consensus_answer": leading_answer,
                "vote_count": vote_count,
                "wrong_models": wrong_models,
                "high_confidence_wrong_models": high_confidence_wrong_models,
                "external_answer": event.get("external_answer"),
                "portal_accepted": event.get("portal_accepted"),
                "metadata": (
                    event.get("metadata")
                    if isinstance(event.get("metadata"), dict)
                    else {}
                ),
                "predictions": [_public_prediction(item) for item in predictions],
            }
        )
    return sorted(cases, key=lambda item: str(item.get("received_at_utc") or ""), reverse=True)


def build_captcha_dataset_zip(
    events: list[dict[str, Any]],
    screenshots_root: Path,
) -> tuple[bytes, int]:
    rows: list[dict[str, Any]] = []
    image_files: list[tuple[str, bytes]] = []
    unavailable = 0
    root = screenshots_root.resolve()
    for event in _canonical_events(events):
        answer = _human_answer(event)
        image_sha256 = str(event.get("image_sha256") or "").lower()
        human_label = event.get("human_label")
        if not answer or not _valid_sha256(image_sha256) or not isinstance(human_label, dict):
            continue
        image_value = event.get("image_path")
        if not isinstance(image_value, str) or not image_value:
            unavailable += 1
            continue
        try:
            image_path = Path(image_value).resolve(strict=True)
        except OSError:
            unavailable += 1
            continue
        if not image_path.is_relative_to(root) or not image_path.is_file():
            unavailable += 1
            continue
        image_bytes = image_path.read_bytes()
        if hashlib.sha256(image_bytes).hexdigest() != image_sha256:
            unavailable += 1
            continue
        filename = f"{image_sha256}.png"
        rows.append(
            {
                "filename": filename,
                "answer": answer,
                "event_id": str(event.get("event_id") or ""),
                "image_sha256": image_sha256,
                "reviewer": str(human_label.get("reviewer") or ""),
                "review_id": str(human_label.get("review_id") or ""),
                "created_at_utc": str(human_label.get("created_at_utc") or ""),
                "note": str(human_label.get("note") or ""),
            }
        )
        image_files.append((f"images/{filename}", image_bytes))
    if unavailable:
        raise ValueError(
            f"{unavailable} CAPTCHA validados no tienen una imagen autorizada disponible."
        )
    if not rows:
        raise ValueError("No hay CAPTCHA validados disponibles para exportar.")

    labels_csv = _csv_bytes(rows, ("filename", "answer"))
    manifest_csv = _csv_bytes(
        rows,
        (
            "filename",
            "answer",
            "event_id",
            "image_sha256",
            "reviewer",
            "review_id",
            "created_at_utc",
            "note",
        ),
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("labels.csv", labels_csv)
        archive.writestr("manifest.csv", manifest_csv)
        for name, image_bytes in image_files:
            archive.writestr(name, image_bytes)
    return output.getvalue(), len(rows)


def _canonical_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_image: dict[str, dict[str, Any]] = {}
    without_hash: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda item: str(item.get("received_at_utc") or "")):
        image_sha256 = str(event.get("image_sha256") or "").lower()
        if _valid_sha256(image_sha256):
            by_image[image_sha256] = event
        else:
            without_hash.append(event)
    return [*by_image.values(), *without_hash]


def _weekly_quality(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        week = _iso_week(event.get("received_at_utc"))
        if week is None:
            continue
        answer = _human_answer(event)
        for prediction in _predictions(event):
            model_name = str(prediction.get("model_name") or "").strip()
            if model_name:
                buckets[week][model_name].append(_prediction_answer(prediction) == answer)
    weekly = []
    for week in sorted(buckets):
        models = {}
        validated = 0
        for model_name, results in sorted(buckets[week].items()):
            correct = sum(results)
            evaluated = len(results)
            validated = max(validated, evaluated)
            models[model_name] = {
                "evaluated": evaluated,
                "correct": correct,
                "accuracy": _ratio(correct, evaluated),
            }
        weekly.append({"week": week, "validated": validated, "models": models})
    return weekly


def _iso_week(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    year, week, _ = parsed.isocalendar()
    return f"{year}-W{week:02d}"


def _human_answer(event: dict[str, Any]) -> str:
    label = event.get("human_label")
    return str(label.get("answer") or "").upper() if isinstance(label, dict) else ""


def _predictions(event: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in event.get("predictions") or [] if isinstance(item, dict)]


def _prediction_answer(prediction: dict[str, Any]) -> str:
    return str(prediction.get("prediction") or "").upper()


def _public_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    return {
        key: prediction.get(key)
        for key in (
            "model_name",
            "prediction",
            "mean_confidence",
            "min_char_confidence",
            "sequence_confidence_product",
            "char_confidences",
            "inference_ms",
            "created_at_utc",
        )
    }


def _numeric_values(values: Any) -> list[float]:
    return [number for value in values if (number := _as_float(value)) is not None]


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _average(values: list[float]) -> float | None:
    return fmean(values) if values else None


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    return {
        "samples": len(values),
        "average": _average(values),
        "p50": _percentile(values, 0.5),
        "p90": _percentile(values, 0.9),
    }


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _csv_bytes(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")
