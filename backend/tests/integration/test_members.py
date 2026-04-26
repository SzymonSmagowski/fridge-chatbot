"""Integration tests for /members (§5.3, members.md MoSCoW).

Covers:
- Auth: missing JWT, mismatched family
- CRUD happy paths + response shape
- Cross-family scoping → 404
- Cache-aside hits + invalidation on writes
- pub/sub frame emission on writes
- Soft-delete (set-inactive / set-active) round-trip
- 200 ms / behavior contract: assignment writes immediately (no confirmation)
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from src.models import Member, MemberStatus
from src.schemas.members import MemberResponse


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_get_members_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/members")
    assert resp.status_code == 401


def test_get_members_with_garbage_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/members", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_get_members_with_user_jwt_returns_401(
    client: TestClient, make_jwt
) -> None:
    """User-JWTs (typ != device) must NOT pass get_device_context."""
    user_jwt = make_jwt(typ="access")
    resp = client.get("/api/members", headers={"Authorization": f"Bearer {user_jwt}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Happy path CRUD
# ---------------------------------------------------------------------------


def test_post_members_creates_active_member_and_returns_201(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/members",
        headers=auth_headers,
        json={"name": "Ola", "color": "sage"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Contract surface — Architect §5.3 MemberResponse
    assert UUID(body["id"])
    assert UUID(body["family_id"])
    assert body["name"] == "Ola"
    assert body["color"] == "sage"
    assert body["status"] == "active"
    assert body["is_setup_owner"] is False
    assert body["google"]["status"] == "not_connected"
    assert body["google"]["email"] is None
    # Validates cleanly against the Pydantic schema (no extra/missing fields).
    MemberResponse.model_validate(body)


def test_get_members_lists_only_active_by_default(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post("/api/members", headers=auth_headers, json={"name": "Mom", "color": "rose"})
    inactive = client.post(
        "/api/members", headers=auth_headers, json={"name": "Old Cat", "color": "stone"}
    ).json()
    client.post(
        f"/api/members/{inactive['id']}/set-inactive", headers=auth_headers
    )

    resp = client.get("/api/members", headers=auth_headers)
    assert resp.status_code == 200
    names = [m["name"] for m in resp.json()]
    assert "Mom" in names
    assert "Old Cat" not in names

    all_resp = client.get("/api/members?status=all", headers=auth_headers)
    assert "Old Cat" in [m["name"] for m in all_resp.json()]


def test_patch_member_updates_name_and_persists(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/members", headers=auth_headers, json={"name": "Mom", "color": "rose"}
    ).json()
    member_id = created["id"]
    resp = client.patch(
        f"/api/members/{member_id}",
        headers=auth_headers,
        json={"name": "Mama", "nickname": "Mum"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Mama"
    assert resp.json()["nickname"] == "Mum"

    # Survives a fresh GET (cache or DB — both should agree).
    fetched = client.get(f"/api/members/{member_id}", headers=auth_headers).json()
    assert fetched["name"] == "Mama"


def test_set_inactive_soft_deletes_member_keeping_history(
    client: TestClient, auth_headers: dict[str, str], db
) -> None:
    """members.md MoSCoW Must: soft delete, name + color preserved."""
    created = client.post(
        "/api/members", headers=auth_headers, json={"name": "Dad", "color": "amber"}
    ).json()
    member_id = created["id"]
    resp = client.post(f"/api/members/{member_id}/set-inactive", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"

    # Row still exists with original name + color (no hard delete).
    row = db.query(Member).filter(Member.id == UUID(member_id)).first()
    assert row is not None
    assert row.name == "Dad"
    assert row.color == "amber"
    assert row.status == MemberStatus.inactive


def test_set_active_reactivates_member(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/members", headers=auth_headers, json={"name": "Ola", "color": "sage"}
    ).json()
    member_id = created["id"]
    client.post(f"/api/members/{member_id}/set-inactive", headers=auth_headers)
    resp = client.post(f"/api/members/{member_id}/set-active", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_post_members_with_empty_name_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/api/members", headers=auth_headers, json={"name": "", "color": "sage"}
    )
    assert resp.status_code == 422


def test_post_members_with_missing_color_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post("/api/members", headers=auth_headers, json={"name": "Ola"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cross-family scoping (§5.3 — uniform 404, never 403)
# ---------------------------------------------------------------------------


def test_get_member_in_other_family_returns_404_not_found_not_403(
    client: TestClient, auth_headers: dict[str, str], make_family
) -> None:
    """Cross-family UUID must produce 404 with `members.not_found`, never 403."""
    _other_fam, _device, _other_token = make_family(family_name="Other Family")
    other_member = client.post(
        "/api/members",
        headers={"Authorization": f"Bearer {_other_token}"},
        json={"name": "Stranger", "color": "ocean"},
    ).json()

    resp = client.get(
        f"/api/members/{other_member['id']}", headers=auth_headers
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "members.not_found"


def test_get_member_with_random_uuid_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get(f"/api/members/{uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "members.not_found"


# ---------------------------------------------------------------------------
# Cache-aside (§7.6) — read serves cached, write invalidates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_members_caches_response_in_redis(
    client: TestClient, auth_headers: dict[str, str], redis_client: Redis, family
) -> None:
    family_id, _device_id, _ = family
    client.post("/api/members", headers=auth_headers, json={"name": "Mom", "color": "rose"})

    # Two GETs — second should be a cache hit (key populated).
    client.get("/api/members", headers=auth_headers)
    keys = await redis_client.keys(f"family:{family_id}:members:*")
    assert keys, "expected cache-aside to populate at least one members:* key"


@pytest.mark.asyncio
async def test_post_members_invalidates_list_cache(
    client: TestClient, auth_headers: dict[str, str], redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    # Prime cache.
    client.get("/api/members", headers=auth_headers)
    primed = await redis_client.keys(f"family:{family_id}:members:*")
    assert primed
    # Write — should drop those keys.
    client.post("/api/members", headers=auth_headers, json={"name": "Ola", "color": "sage"})
    after = await redis_client.keys(f"family:{family_id}:members:*")
    assert after == [], "POST /members should evict family:{id}:members:*"


# ---------------------------------------------------------------------------
# Pub/sub (§5.11) — every covered write emits a frame
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_members_publishes_member_created_event(
    client: TestClient,
    auth_headers: dict[str, str],
    family,
    family_event_collector,
) -> None:
    family_id, _, _ = family
    async with family_event_collector(family_id) as collector:
        client.post(
            "/api/members", headers=auth_headers, json={"name": "Ola", "color": "sage"}
        )
        frames = await collector.wait_for(1)
    assert len(frames) >= 1
    frame = frames[0]
    assert frame["type"] == "member.created"
    assert frame["entity"] == "members"
    assert UUID(frame["id"])
    assert frame["actor"] == "rest"
    assert "ts" in frame


@pytest.mark.asyncio
async def test_set_inactive_publishes_member_updated_event(
    client: TestClient,
    auth_headers: dict[str, str],
    family,
    family_event_collector,
) -> None:
    family_id, _, _ = family
    created = client.post(
        "/api/members", headers=auth_headers, json={"name": "Mom", "color": "rose"}
    ).json()
    async with family_event_collector(family_id) as collector:
        client.post(f"/api/members/{created['id']}/set-inactive", headers=auth_headers)
        frames = await collector.wait_for(1)
    assert len(frames) >= 1
    # §5.11: set-inactive emits the granular `member.set-inactive` frame, not the
    # generic `member.updated`. Both shapes are spec-listed; the more specific
    # one wins so kiosks can tell deactivations apart from rename/recolor edits.
    assert frames[0]["type"] == "member.set-inactive"
    assert frames[0]["entity"] == "members"
    assert frames[0]["id"] == created["id"]
