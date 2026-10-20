from __future__ import annotations

from threading import Event, RLock

from appointment_bot.configuration.loading import load_runtime_settings
from appointment_bot.core.whatsapp_delivery import WhatsAppAttemptContext, masked_whatsapp_recipient
from appointment_bot.db.whatsapp_delivery import (
    complete_delivery_attempt,
    initialize_delivery_attempt,
    record_delivery_event,
    start_delivery_attempt,
)


class WhatsAppDeliveryRecorder:
    def __init__(self, job, attempt, settings, selection=None, inherited=None):
        self.dispatched = False
        self.cancelled = Event()
        self.lock = RLock()
        self.settings = settings
        self.attempt = attempt
        self.selected = selection
        self.inherited = inherited or {}
        self.active = []
        self.states = {}
        self.attempt_id = start_delivery_attempt(
            job["job_key"], attempt.recipient, settings=settings
        )

    def initialize(self, draft, components):
        self.attempt.message_id = str(draft["message_id"])
        self.attempt.recipient = masked_whatsapp_recipient(
            draft.get("recipient_phone"), draft.get("recipient_username")
        )
        keys = {key for key, _label in components}
        if self.selected is not None and not set(self.selected).issubset(keys):
            raise ValueError("La recuperacion ya no coincide con el paquete congelado.")
        manifest = []
        for key, label in components:
            state = "not_attempted"
            if self.selected is not None and key not in self.selected:
                state = self.inherited.get(key, "uncertain")
                if state != "confirmed":
                    raise ValueError("No se puede omitir un componente sin confirmar.")
            self.states[key] = state
            manifest.append({"key": key, "label": label, "state": state})
        initialize_delivery_attempt(
            self.attempt_id,
            self.attempt.message_id,
            self.attempt.recipient,
            manifest,
            settings=self.settings,
        )

    def complete(self):
        complete_delivery_attempt(self.attempt_id, settings=self.settings)

    def cancel(self):
        with self.lock:
            self.cancelled.set()

    def start(self, keys):
        with self.lock:
            if self.cancelled.is_set():
                raise RuntimeError("El intento vencio; no se iniciaran mas componentes.")
            if not keys or any(key not in self.states for key in keys):
                raise ValueError("El envio no coincide con el manifiesto persistido.")
            if self.selected is not None and any(key not in self.selected for key in keys):
                raise ValueError("El componente no pertenece a la recuperacion autorizada.")
            if any(self.states[key] != "not_attempted" for key in keys):
                raise ValueError("No se puede repetir un componente iniciado o confirmado.")
            record_delivery_event(
                self.attempt_id,
                keys,
                "uncertain",
                None,
                None,
                settings=self.settings,
                guard_running=True,
            )
            self.active = keys
            self.states.update(dict.fromkeys(keys, "uncertain"))
            self.attempt.advance("interaction_started", component=",".join(keys))

    def confirm(self, keys, outgoing_id):
        keys = [key for key in keys if self.states.get(key) != "confirmed"]
        if not keys:
            return
        if any(self.states.get(key) != "uncertain" for key in keys):
            raise ValueError("No se puede confirmar un componente sin intento de envio.")
        record_delivery_event(
            self.attempt_id, keys, "confirmed", None, outgoing_id, settings=self.settings
        )
        self.states.update(dict.fromkeys(keys, "confirmed"))

    def evidence(self, path):
        self.attempt.evidence_path = path
        for key in self.active:
            record_delivery_event(
                self.attempt_id, [key], self.states[key], path, None, settings=self.settings
            )


def manual_delivery_recorder(draft, job_kind):
    settings = load_runtime_settings(require_login=False)
    attempt = WhatsAppAttemptContext(
        job_key=f"manual:{draft['message_id']}",
        job_kind=job_kind,
        recipient=masked_whatsapp_recipient(
            draft.get("recipient_phone"), draft.get("recipient_username")
        ),
    )
    return WhatsAppDeliveryRecorder({"job_key": None}, attempt, settings)
