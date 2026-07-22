from __future__ import annotations

FOCUSED_PRIORITY_THRESHOLD = 100
EXCLUSIVE_PRIORITY_THRESHOLD = 200


def is_exclusive_priority(priority: int) -> bool:
    return priority >= EXCLUSIVE_PRIORITY_THRESHOLD
