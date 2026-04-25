"""Sanity smoke tests for the test harness itself.

These keep the conftest healthy: if /health stops returning 200, every
downstream integration test will fail with a confusing error — better to fail
this one obvious test first.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_smoke_health_endpoint_returns_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy", "service": "fridge-chatbot-backend"}


def test_smoke_unauth_endpoint_rejects_missing_token(client: TestClient) -> None:
    """Bare GET /family without Authorization header → 401."""
    resp = client.get("/family")
    assert resp.status_code == 401
