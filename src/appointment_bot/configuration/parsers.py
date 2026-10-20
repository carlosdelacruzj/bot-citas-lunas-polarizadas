from datetime import time as datetime_time


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"Invalid boolean value: {value!r}")


def _parse_int(value: str | None, *, default: int, minimum: int | None = None) -> int:
    if value is None or value == "":
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value: {value!r}") from exc

    if minimum is not None and parsed < minimum:
        raise ValueError(f"Integer value must be greater than or equal to {minimum}: {value!r}")

    return parsed


def _parse_float(
    value: str | None,
    *,
    default: float,
    minimum: float | None = None,
) -> float:
    if value is None or value == "":
        return default

    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value: {value!r}") from exc

    if minimum is not None and parsed < minimum:
        raise ValueError(f"Numeric value must be greater than or equal to {minimum}: {value!r}")

    return parsed


def _parse_int_list(value: str | None, *, default: tuple[int, ...]) -> tuple[int, ...]:
    if value is None or value.strip() == "":
        return default
    try:
        parsed = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer list value: {value!r}") from exc
    if not parsed or any(item < 0 for item in parsed):
        raise ValueError(f"Integer list must contain non-negative values: {value!r}")
    return parsed


def _parse_evidence_profile(value: str | None) -> str:
    profile = (value or "custom").strip().lower()
    if not profile:
        return "custom"
    if profile not in {"custom", "fast", "diagnostic"}:
        raise ValueError("EVIDENCE_PROFILE must be custom, fast, or diagnostic.")
    return profile


def _parse_time_windows(
    value: str | None,
    *,
    default: tuple[tuple[datetime_time, datetime_time], ...],
) -> tuple[tuple[datetime_time, datetime_time], ...]:
    if value is None or value.strip() == "":
        return default

    windows = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            start_text, end_text = (part.strip() for part in item.split("-", maxsplit=1))
            start = datetime_time.fromisoformat(start_text)
            end = datetime_time.fromisoformat(end_text)
        except ValueError as exc:
            raise ValueError(
                f"Invalid time window. Use HH:MM-HH:MM entries separated by commas: {value!r}"
            ) from exc
        if start >= end:
            raise ValueError(f"Time window start must be before end: {item!r}")
        windows.append((start, end))

    return tuple(windows)


def _parse_time(value: str | None, *, default: datetime_time) -> datetime_time:
    if value is None or value.strip() == "":
        return default
    try:
        return datetime_time.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid time. Use HH:MM: {value!r}") from exc
