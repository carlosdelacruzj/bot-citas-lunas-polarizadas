from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

DEFAULT_CONTENT_STORE = Path(".runtime/whatsapp-package-content")


def copy_deduplicated_file(
    source: Path,
    destination: Path,
    *,
    content_store: Path | None = None,
) -> Path:
    source = source.resolve()
    requested_destination = destination
    destination = destination.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)

    resolved_store = (content_store or DEFAULT_CONTENT_STORE).resolve()
    canonical = _canonical_file(source, resolved_store)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _link_or_copy(canonical, destination)
    return requested_destination


def deduplicate_files_in_place(
    paths: Iterable[Path],
    *,
    content_store: Path | None = None,
) -> dict[str, int]:
    summary = {"inspected": 0, "linked": 0, "already_linked": 0, "copied": 0}
    resolved_store = (content_store or DEFAULT_CONTENT_STORE).resolve()
    for value in paths:
        path = value.resolve()
        if not path.is_file():
            continue
        summary["inspected"] += 1
        canonical = _canonical_file(path, resolved_store)
        if os.path.samefile(path, canonical):
            summary["already_linked"] += 1
            continue

        replacement = path.with_name(f".{path.name}.{uuid4().hex}.dedup")
        try:
            linked = _link_or_copy(canonical, replacement)
            os.replace(replacement, path)
        finally:
            replacement.unlink(missing_ok=True)
        summary["linked" if linked else "copied"] += 1
    return summary


def _canonical_file(source: Path, content_store: Path) -> Path:
    digest = _sha256(source)
    canonical = content_store / digest[:2] / digest
    if canonical.exists():
        _validate_canonical(canonical, digest)
        return canonical

    canonical.parent.mkdir(parents=True, exist_ok=True)
    temporary = canonical.with_name(f".{canonical.name}.{uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        _validate_canonical(temporary, digest)
        if not canonical.exists():
            os.replace(temporary, canonical)
    finally:
        temporary.unlink(missing_ok=True)
    _validate_canonical(canonical, digest)
    return canonical


def _link_or_copy(source: Path, destination: Path) -> bool:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
        return False
    return True


def _validate_canonical(path: Path, expected_digest: str) -> None:
    if not path.is_file() or _sha256(path) != expected_digest:
        raise RuntimeError(f"El archivo canonico deduplicado esta corrupto: {path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
