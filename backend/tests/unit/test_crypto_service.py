"""Unit tests for src/services/crypto_service.py — Fernet round-trip + error paths."""
from __future__ import annotations

import pytest

from src.core.settings import Settings
from src.services.crypto_service import CryptoService


def test_encrypt_decrypt_round_trip_preserves_plaintext() -> None:
    svc = CryptoService(Settings())
    plaintext = "google-refresh-token-1234//abc"
    cipher = svc.encrypt(plaintext)
    assert isinstance(cipher, bytes)
    assert cipher != plaintext.encode()
    assert svc.decrypt(cipher) == plaintext


def test_decrypt_with_tampered_ciphertext_raises_value_error() -> None:
    svc = CryptoService(Settings())
    cipher = svc.encrypt("hello")
    tampered = cipher[:-1] + bytes([(cipher[-1] + 1) % 256])
    with pytest.raises(ValueError):
        svc.decrypt(tampered)


def test_ctor_without_fernet_key_raises_value_error() -> None:
    settings = Settings()
    settings.FERNET_KEY = ""
    with pytest.raises(ValueError):
        CryptoService(settings)
