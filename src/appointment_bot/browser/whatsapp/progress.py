from __future__ import annotations

from contextvars import ContextVar

_last_evidence = ContextVar("whatsapp_last_evidence", default=None)
_progress = ContextVar("whatsapp_delivery_progress", default=None)


def set_delivery_progress(progress):
    _last_evidence.set(None)
    return _progress.set(progress)


def reset_delivery_progress(token):
    _progress.reset(token)


def plan_delivery(draft, components):
    progress = _progress.get()
    if progress is not None:
        progress.initialize(draft, components)


def start_components(keys):
    progress = _progress.get()
    if progress is not None:
        progress.start(keys)


def confirm_components(keys, outgoing_id=None):
    progress = _progress.get()
    if progress is not None:
        progress.confirm(keys, outgoing_id)


def latest_evidence_path():
    return _last_evidence.get()


def record_evidence(path):
    _last_evidence.set(path)
    progress = _progress.get()
    if progress is not None:
        progress.evidence(path)


def selected_components(keys):
    progress = _progress.get()
    if progress is None or progress.selected is None:
        return keys
    return [key for key in keys if key in progress.selected]
