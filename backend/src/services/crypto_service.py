"""Fernet encrypt/decrypt for at-rest secrets (Google refresh tokens).

D7: Fernet (AES-128-CBC + HMAC-SHA256) is the simplest symmetric AEAD that
ships with `cryptography`. Future key rotation: swap to MultiFernet when needed.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from src.core.settings import Settings


class CryptoService:
    def __init__(self, settings: Settings) -> None:
        key = settings.FERNET_KEY
        if not key:
            raise ValueError("FERNET_KEY is required for CryptoService")
        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt: invalid token") from exc
