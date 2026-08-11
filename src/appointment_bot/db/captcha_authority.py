from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _settings, init_database


@dataclass(frozen=True)
class CaptchaAuthorityControl:
    mode: str
    canary_limit: int
    local_decisions: int
    local_confirmed: int
    local_rejected: int
    fallback_decisions: int
    min_char_confidence: float
    sequence_confidence_product: float
    timeout_ms: int
    circuit_state: str
    circuit_reason: str | None
    circuit_opened_at: datetime | None
    updated_at: datetime
    updated_by: str
    activated_at: datetime | None

    @property
    def remaining_local_decisions(self) -> int:
        return max(self.canary_limit - self.local_decisions, 0)

    @property
    def local_admission_open(self) -> bool:
        return (
            self.mode == "canary"
            and self.circuit_state == "closed"
            and self.remaining_local_decisions > 0
        )


@dataclass(frozen=True)
class CaptchaAuthorityDecision:
    decision_id: str
    event_id: str
    source: str
    fallback_reason: str | None


def get_captcha_authority_control(
    settings: Settings | None = None,
) -> CaptchaAuthorityControl:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            "SELECT * FROM captcha_authority_control WHERE id = 1"
        ).fetchone()
    if row is None:
        raise RuntimeError("captcha_authority_control is missing")
    return _control(row)


def update_captcha_authority_control(
    *,
    mode: str,
    canary_limit: int,
    min_char_confidence: float,
    sequence_confidence_product: float,
    timeout_ms: int,
    updated_by: str,
    reset_circuit: bool = False,
    reset_counters: bool = False,
    settings: Settings | None = None,
) -> CaptchaAuthorityControl:
    if mode not in {"2captcha", "canary"}:
        raise ValueError("mode must be 2captcha or canary")
    if not 1 <= canary_limit <= 100:
        raise ValueError("canary_limit must be between 1 and 100")
    for name, value in (
        ("min_char_confidence", min_char_confidence),
        ("sequence_confidence_product", sequence_confidence_product),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if not 100 <= timeout_ms <= 2000:
        raise ValueError("timeout_ms must be between 100 and 2000")
    resolved = _settings(settings)
    init_database(resolved)
    actor = updated_by.strip()[:64] or "admin_api"
    now = datetime.now(UTC)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            UPDATE captcha_authority_control
            SET mode = %s, canary_limit = %s, min_char_confidence = %s,
                sequence_confidence_product = %s, timeout_ms = %s,
                local_decisions = CASE WHEN %s THEN 0 ELSE local_decisions END,
                local_confirmed = CASE WHEN %s THEN 0 ELSE local_confirmed END,
                local_rejected = CASE WHEN %s THEN 0 ELSE local_rejected END,
                fallback_decisions = CASE WHEN %s THEN 0 ELSE fallback_decisions END,
                circuit_state = CASE WHEN %s THEN 'closed' ELSE circuit_state END,
                circuit_reason = CASE WHEN %s THEN NULL ELSE circuit_reason END,
                circuit_opened_at = CASE WHEN %s THEN NULL ELSE circuit_opened_at END,
                activated_at = CASE
                    WHEN %s = 'canary' AND (mode <> 'canary' OR %s) THEN %s
                    ELSE activated_at
                END,
                updated_at = %s, updated_by = %s
            WHERE id = 1
            RETURNING *
            """,
            (
                mode,
                canary_limit,
                min_char_confidence,
                sequence_confidence_product,
                timeout_ms,
                reset_counters,
                reset_counters,
                reset_counters,
                reset_counters,
                reset_circuit,
                reset_circuit,
                reset_circuit,
                mode,
                reset_counters,
                now,
                now,
                actor,
            ),
        ).fetchone()
    return _control(row)


def record_captcha_authority_decision(
    *,
    event_id: str,
    run_id: str | None,
    order_id: str | None,
    attempt_number: int,
    prediction: str | None,
    mean_confidence: float | None,
    min_char_confidence: float | None,
    sequence_confidence_product: float | None,
    inference_ms: float | None,
    request_ms: float | None,
    fallback_reason: str | None,
    settings: Settings | None = None,
) -> CaptchaAuthorityDecision:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        existing = connection.execute(
            """
            SELECT decision_id, event_id, source, fallback_reason
            FROM captcha_authority_decisions WHERE event_id = %s
            """,
            (event_id,),
        ).fetchone()
        if existing is not None:
            return _decision(existing)

        control = connection.execute(
            "SELECT * FROM captcha_authority_control WHERE id = 1 FOR UPDATE"
        ).fetchone()
        reason = fallback_reason
        if reason is None and control["mode"] != "canary":
            reason = "mode_2captcha"
        if reason is None and control["circuit_state"] == "open":
            reason = "circuit_open"
        if reason is None and int(control["local_decisions"]) >= int(
            control["canary_limit"]
        ):
            reason = "canary_limit_reached"
        if reason is None and (
            min_char_confidence is None
            or min_char_confidence < float(control["min_char_confidence"])
        ):
            reason = "min_char_confidence"
        if reason is None and (
            sequence_confidence_product is None
            or sequence_confidence_product
            < float(control["sequence_confidence_product"])
        ):
            reason = "sequence_confidence_product"

        source = "v6" if reason is None else "2captcha"
        decision_id = f"captcha-decision-{uuid4().hex}"
        prediction_sha256 = (
            hashlib.sha256(prediction.encode("ascii")).hexdigest()
            if prediction is not None
            else None
        )
        row = connection.execute(
            """
            INSERT INTO captcha_authority_decisions (
                decision_id, event_id, run_id, order_id, attempt_number,
                source, fallback_reason, prediction_sha256, mean_confidence,
                min_char_confidence, sequence_confidence_product,
                inference_ms, request_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING decision_id, event_id, source, fallback_reason
            """,
            (
                decision_id,
                event_id,
                run_id,
                order_id,
                attempt_number,
                source,
                reason,
                prediction_sha256,
                mean_confidence,
                min_char_confidence,
                sequence_confidence_product,
                inference_ms,
                request_ms,
            ),
        ).fetchone()
        counter = "local_decisions" if source == "v6" else "fallback_decisions"
        connection.execute(
            f"UPDATE captcha_authority_control SET {counter} = {counter} + 1 WHERE id = 1"
        )
    return _decision(row)


def resolve_captcha_authority_decision(
    event_id: str,
    *,
    portal_outcome: str,
    settings: Settings | None = None,
) -> None:
    resolved = _settings(settings)
    init_database(resolved)
    portal_accepted = (
        True
        if portal_outcome == "confirmed"
        else False
        if portal_outcome == "captcha_invalid"
        else None
    )
    now = datetime.now(UTC)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            UPDATE captcha_authority_decisions
            SET portal_outcome = %s, portal_accepted = %s, resolved_at = %s
            WHERE event_id = %s AND resolved_at IS NULL
            RETURNING source
            """,
            (portal_outcome[:40], portal_accepted, now, event_id),
        ).fetchone()
        if row is None or row["source"] != "v6":
            return
        if portal_outcome == "confirmed":
            connection.execute(
                """
                UPDATE captcha_authority_control
                SET local_confirmed = local_confirmed + 1 WHERE id = 1
                """
            )
            return
        if portal_outcome == "captcha_invalid":
            connection.execute(
                """
                UPDATE captcha_authority_control
                SET local_rejected = local_rejected + 1,
                    circuit_state = 'open', circuit_reason = 'captcha_invalid',
                    circuit_opened_at = %s, updated_at = %s,
                    updated_by = 'worker_breaker'
                WHERE id = 1
                """,
                (now, now),
            )
        elif portal_outcome == "unknown":
            trip_captcha_authority_circuit(
                "reservation_unconfirmed",
                settings=resolved,
                connection=connection,
            )


def trip_captcha_authority_circuit(
    reason: str,
    *,
    settings: Settings | None = None,
    connection=None,
) -> None:
    resolved = _settings(settings)
    now = datetime.now(UTC)
    safe_reason = reason.strip()[:120] or "local_solver_failure"
    if connection is not None:
        connection.execute(
            """
            UPDATE captcha_authority_control
            SET circuit_state = 'open', circuit_reason = %s,
                circuit_opened_at = %s, updated_at = %s,
                updated_by = 'worker_breaker'
            WHERE id = 1 AND circuit_state = 'closed'
            """,
            (safe_reason, now, now),
        )
        return
    init_database(resolved)
    with _connection(_database_url(resolved)) as own_connection:
        trip_captcha_authority_circuit(
            safe_reason,
            settings=resolved,
            connection=own_connection,
        )


def _control(row) -> CaptchaAuthorityControl:
    return CaptchaAuthorityControl(
        mode=str(row["mode"]),
        canary_limit=int(row["canary_limit"]),
        local_decisions=int(row["local_decisions"]),
        local_confirmed=int(row["local_confirmed"]),
        local_rejected=int(row["local_rejected"]),
        fallback_decisions=int(row["fallback_decisions"]),
        min_char_confidence=float(row["min_char_confidence"]),
        sequence_confidence_product=float(row["sequence_confidence_product"]),
        timeout_ms=int(row["timeout_ms"]),
        circuit_state=str(row["circuit_state"]),
        circuit_reason=row["circuit_reason"],
        circuit_opened_at=row["circuit_opened_at"],
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
        activated_at=row["activated_at"],
    )


def _decision(row) -> CaptchaAuthorityDecision:
    return CaptchaAuthorityDecision(
        decision_id=str(row["decision_id"]),
        event_id=str(row["event_id"]),
        source=str(row["source"]),
        fallback_reason=row["fallback_reason"],
    )
