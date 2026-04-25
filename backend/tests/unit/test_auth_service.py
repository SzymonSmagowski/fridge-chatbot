"""Unit tests for AuthService — JWT encode/decode for device tokens."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.settings import Settings
from src.services.auth_service import AuthService


def test_create_device_token_round_trips_with_decode() -> None:
    svc = AuthService(Settings())
    device_id = uuid4()
    family_id = uuid4()
    token = svc.create_device_token(device_id=device_id, family_id=family_id)
    payload = svc.decode_token(token)
    assert payload["sub"] == str(device_id)
    assert payload["family_id"] == str(family_id)
    assert payload["typ"] == "device"


def test_decode_token_with_garbage_raises_401() -> None:
    svc = AuthService(Settings())
    with pytest.raises(HTTPException) as exc:
        svc.decode_token("garbage")
    assert exc.value.status_code == 401


def test_decode_token_signed_with_other_secret_raises_401() -> None:
    real = AuthService(Settings())
    forged_settings = Settings()
    forged_settings.SECRET_KEY = "different-secret-key-not-the-real-one"
    forged = AuthService(forged_settings)
    bad_token = forged.create_device_token(device_id=uuid4(), family_id=uuid4())
    with pytest.raises(HTTPException):
        real.decode_token(bad_token)
