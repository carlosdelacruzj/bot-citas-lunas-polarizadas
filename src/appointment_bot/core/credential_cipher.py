from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

TOKEN_PREFIX = "enc:v1:"


class CredentialDecryptionError(ValueError):
    pass


class CredentialCipher:
    """Encrypt recoverable credentials with key rotation support."""

    def __init__(self, keys: tuple[str, ...]) -> None:
        if not keys:
            raise ValueError(
                "APPOINTMENT_CREDENTIAL_KEYS is required to store or read portal credentials."
            )
        try:
            self._fernets = tuple(Fernet(key.encode("ascii")) for key in keys)
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError(
                "APPOINTMENT_CREDENTIAL_KEYS must contain valid Fernet keys."
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        token = self._fernets[0].encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{TOKEN_PREFIX}{token}"

    def decrypt(self, value: str) -> str:
        if not value.startswith(TOKEN_PREFIX):
            raise CredentialDecryptionError("A portal credential is not encrypted.")
        token = value.removeprefix(TOKEN_PREFIX).encode("ascii")
        for fernet in self._fernets:
            try:
                return fernet.decrypt(token).decode("utf-8")
            except InvalidToken:
                continue
        raise CredentialDecryptionError(
            "A portal credential cannot be decrypted with APPOINTMENT_CREDENTIAL_KEYS."
        )
