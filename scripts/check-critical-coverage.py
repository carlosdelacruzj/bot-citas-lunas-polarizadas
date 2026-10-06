from __future__ import annotations

import json
import sys
from pathlib import Path

CRITICAL_THRESHOLDS = {
    "src/appointment_bot/core/service_packages.py": 70.0,
    "src/appointment_bot/core/whatsapp_delivery.py": 60.0,
    "src/appointment_bot/db/browser_ownership.py": 70.0,
    "src/appointment_bot/db/migrations.py": 45.0,
    "src/appointment_bot/db/reservations.py": 68.0,
    "src/appointment_bot/manual_session/session.py": 30.0,
    "src/appointment_bot/reservation_engine/reservation_submit.py": 50.0,
    "src/appointment_bot/reservation_engine/slot_evidence.py": 68.0,
    "src/appointment_bot/services/order_preflight.py": 60.0,
    "src/appointment_bot/services/order_transitions.py": 90.0,
    "src/appointment_bot/services/whatsapp_automation.py": 20.0,
    "src/appointment_bot/worker/lease.py": 80.0,
}


def _normalized_files(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("Coverage JSON does not contain a files mapping.")
    return {str(path).replace("\\", "/"): value for path, value in files.items()}


def _migration_coverage(files: dict[str, dict[str, object]]) -> float:
    paths = {
        "src/appointment_bot/db/migrations.py",
        "src/appointment_bot/db/schema_definition.py",
        "src/appointment_bot/db/schema_validation.py",
    }
    paths.update(
        path.as_posix()
        for path in Path("src/appointment_bot/db/migration_steps").glob("*.py")
    )
    covered = 0
    total = 0
    for path in sorted(paths):
        entry = files.get(path)
        if not isinstance(entry, dict) or not isinstance(entry.get("summary"), dict):
            raise ValueError(f"Migration coverage missing for {path}")
        summary = entry["summary"]
        covered += int(summary["covered_lines"]) + int(summary.get("covered_branches", 0))
        total += int(summary["num_statements"]) + int(summary.get("num_branches", 0))
    return 100.0 * covered / total if total else 100.0


def main() -> int:
    report_path = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/ci/coverage.json")
    if not report_path.is_file():
        print(f"Critical coverage report not found: {report_path}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        files = _normalized_files(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not read critical coverage report: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    print("Critical backend coverage (statements and branches):")
    for path, minimum in CRITICAL_THRESHOLDS.items():
        entry = files.get(path)
        if not isinstance(entry, dict):
            failures.append(f"{path}: missing from report")
            continue
        summary = entry.get("summary")
        if not isinstance(summary, dict):
            failures.append(f"{path}: missing summary")
            continue
        measured = float(summary.get("percent_covered", 0.0))
        if path == "src/appointment_bot/db/migrations.py":
            try:
                measured = _migration_coverage(files)
            except (KeyError, TypeError, ValueError) as exc:
                failures.append(str(exc))
                continue
            print("  Migration coverage includes schema helpers and all historical steps.")
        print(f"- {path}: {measured:.2f}% (minimum {minimum:.2f}%)")
        if measured + 1e-9 < minimum:
            failures.append(f"{path}: {measured:.2f}% is below {minimum:.2f}%")

    if failures:
        print("Critical coverage gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Critical coverage gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
