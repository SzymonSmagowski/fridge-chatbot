"""Unit tests for EventTargetResolver — verifies the four §7.4 fan-out rules.

Rules:
  1. assignee set, no cars → 1 target = the assignee
  2. assignee set + cars → 1 target = the assignee (cars decorate; no extra fan-out)
  3. assignee null, no cars → fan out to every active member (with Google → pending; without → skipped)
  4. assignee null + cars → fan out to every active member

Touches the DB (it's a thin layer over a SELECT) but is unit-shaped: no HTTP,
no cache, no pub/sub.
"""
from __future__ import annotations


from src.models import (
    GoogleToken,
    GoogleTokenStatus,
    Member,
    MemberStatus,
)
from src.services.event_target_resolver import EventTargetResolver


def _make_member(db, family_id, name, *, status=MemberStatus.active, with_google=False) -> Member:
    m = Member(family_id=family_id, name=name, color="sage", status=status)
    db.add(m)
    db.commit()
    db.refresh(m)
    if with_google:
        db.add(
            GoogleToken(
                member_id=m.id,
                refresh_token_encrypted=b"ct",
                google_sub="g",
                google_email="g@g.g",
                scope="x",
                status=GoogleTokenStatus.connected,
            )
        )
        db.commit()
    return m


def test_resolve_with_assignee_no_cars_returns_single_target(
    db, family
) -> None:
    """Rule 1: single assignee with Google → one pending target."""
    family_id, _, _ = family
    mom = _make_member(db, family_id, "Mom", with_google=True)
    resolver = EventTargetResolver(db, family_id)
    plans = resolver.resolve_targets(assignee_member_id=mom.id, car_ids=[])
    assert len(plans) == 1
    assert plans[0].member_id == mom.id
    assert plans[0].skipped_reason is None


def test_resolve_with_assignee_no_google_marks_skipped(db, family) -> None:
    """Rule 1 variant: assignee without Google → skipped target with reason."""
    family_id, _, _ = family
    dad = _make_member(db, family_id, "Dad", with_google=False)
    resolver = EventTargetResolver(db, family_id)
    plans = resolver.resolve_targets(assignee_member_id=dad.id, car_ids=[])
    assert len(plans) == 1
    assert plans[0].skipped_reason == "no_google_connection"


def test_resolve_with_assignee_and_cars_still_returns_single_target(
    db, family
) -> None:
    """Rule 2: assignee + cars → only one target (no double-write)."""
    from uuid import uuid4
    family_id, _, _ = family
    mom = _make_member(db, family_id, "Mom", with_google=True)
    _make_member(db, family_id, "Dad", with_google=True)
    resolver = EventTargetResolver(db, family_id)
    plans = resolver.resolve_targets(
        assignee_member_id=mom.id, car_ids=[uuid4()]
    )
    assert len(plans) == 1
    assert plans[0].member_id == mom.id


def test_resolve_no_assignee_no_cars_fans_out_to_all_active(db, family) -> None:
    """Rule 3: no assignee, no cars → every active member receives a target."""
    family_id, _, _ = family
    mom = _make_member(db, family_id, "Mom", with_google=True)
    dad = _make_member(db, family_id, "Dad", with_google=True)
    _make_member(
        db, family_id, "Old", status=MemberStatus.inactive, with_google=True
    )
    resolver = EventTargetResolver(db, family_id)
    plans = resolver.resolve_targets(assignee_member_id=None, car_ids=[])
    member_ids = {p.member_id for p in plans}
    assert member_ids == {mom.id, dad.id}


def test_resolve_no_assignee_with_cars_fans_out_to_all_active(db, family) -> None:
    """Rule 4: car-only event still fans out to every active member."""
    from uuid import uuid4
    family_id, _, _ = family
    mom = _make_member(db, family_id, "Mom", with_google=True)
    dad = _make_member(db, family_id, "Dad", with_google=False)
    resolver = EventTargetResolver(db, family_id)
    plans = resolver.resolve_targets(
        assignee_member_id=None, car_ids=[uuid4()]
    )
    by_member = {p.member_id: p for p in plans}
    assert mom.id in by_member
    assert dad.id in by_member
    assert by_member[mom.id].skipped_reason is None
    assert by_member[dad.id].skipped_reason == "no_google_connection"


def test_resolve_assignee_in_other_family_returns_empty(db, family, make_family) -> None:
    """Cross-family assignee_member_id is filtered out — empty plan, NOT crash."""
    family_id, _, _ = family
    other_family_id, _, _ = make_family()
    intruder = _make_member(db, other_family_id, "Intruder", with_google=True)
    resolver = EventTargetResolver(db, family_id)
    plans = resolver.resolve_targets(
        assignee_member_id=intruder.id, car_ids=[]
    )
    assert plans == []
