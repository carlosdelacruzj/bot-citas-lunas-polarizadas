from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WhatsAppInteractionPhase = Literal[
    "pre_interaction",
    "interaction_started",
    "confirmation_observed",
    "confirmation_persisted",
]
WhatsAppFailureStatus = Literal["failed", "uncertain"]

_PHASE_RANK: dict[WhatsAppInteractionPhase, int] = {
    "pre_interaction": 0,
    "interaction_started": 1,
    "confirmation_observed": 2,
    "confirmation_persisted": 3,
}
_PROVEN_PRE_INTERACTION_STATUSES = {
    "chat_unavailable",
    "invalid_recipient",
    "login_required",
    "recipient_ambiguous",
    "recipient_chat_blocked",
    "recipient_mismatch",
    "recipient_not_configured",
    "recipient_not_found",
}


@dataclass
class WhatsAppAttemptContext:
    job_key: str
    job_kind: str
    recipient: str
    phase: WhatsAppInteractionPhase = "pre_interaction"
    component: str = "preparation"
    message_id: str | None = None
    evidence_path: str | None = None

    def advance(
        self,
        phase: WhatsAppInteractionPhase,
        *,
        component: str | None = None,
        message_id: str | None = None,
        evidence_path: str | None = None,
    ) -> None:
        if _PHASE_RANK[phase] > _PHASE_RANK[self.phase]:
            self.phase = phase
        if component:
            self.component = component
        if message_id:
            self.message_id = message_id
        if evidence_path:
            self.evidence_path = evidence_path

    def absorb_result(self, result: dict[str, object]) -> None:
        result_status = str(result.get("status") or "unknown")
        if result.get("sent"):
            self.advance("confirmation_observed")
        elif (
            result_status in _PROVEN_PRE_INTERACTION_STATUSES
            and _PHASE_RANK[self.phase] <= _PHASE_RANK["interaction_started"]
        ):
            self.phase = "pre_interaction"
        else:
            self.advance("interaction_started")
        evidence_path = str(result.get("evidence_path") or "").strip()
        if evidence_path:
            self.evidence_path = evidence_path
        component = _result_component(self.job_kind, result)
        if component:
            self.component = component

    @property
    def failure_status(self) -> WhatsAppFailureStatus:
        return "failed" if self.phase == "pre_interaction" else "uncertain"

    def failure_detail(self, message: str) -> str:
        evidence = self.evidence_path or "no_disponible"
        message_id = self.message_id or "no_asignado"
        return (
            f"{message} Fase: {self.phase}. Componente: {self.component}. "
            f"Destinatario: {self.recipient}. Evidencia local: {evidence}. "
            f"Contexto: kind={self.job_kind}, job_key={self.job_key}, "
            f"message_id={message_id}."
        )


def masked_whatsapp_recipient(phone_value: str | None, username_value: str | None) -> str:
    phone = "".join(
        character for character in str(phone_value or "") if character.isdigit()
    )
    if phone:
        return f"***{phone[-4:]}"
    username = str(username_value or "").strip()
    if username:
        suffix = username[-2:] if len(username) > 2 else "**"
        return f"@***{suffix.lstrip('@')}"
    return "no_configurado"


def _result_component(job_kind: str, result: dict[str, object]) -> str:
    components = result.get("delivery_components")
    if isinstance(components, dict):
        for state in ("uncertain", "not_attempted"):
            for key, value in components.items():
                if str(value) == state:
                    return str(key)
    return {
        "reservation_album": "album",
        "post_payment_followup": "documents_and_text",
        "daily_slot_summary": "daily_summary",
        "registration_notice": "message",
        "appointment_reminder": "message",
    }.get(job_kind, "send")


__all__ = ["WhatsAppAttemptContext", "masked_whatsapp_recipient"]
