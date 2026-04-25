"""EventTargetResolver — encapsulates the §7.4 fan-out rules.

Rules (resolved by Architect):
  1. assignee_member_id set, no cars → 1 target = the assignee.
  2. assignee_member_id set + cars  → 1 target = the assignee (cars decorate
     the title only; we do not double-write to other members).
  3. assignee_member_id null, no cars → fan out to every active member with a
     Google connection.
  4. assignee_member_id null + cars → fan out to every active member (D5/cars
     spec) — car name appears in title.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from src.models import GoogleToken, GoogleTokenStatus, Member, MemberStatus


@dataclass(frozen=True)
class EventTargetPlan:
    member_id: UUID
    skipped_reason: str | None  # None means we should attempt a write


class EventTargetResolver:
    def __init__(self, db: Session, family_id: UUID) -> None:
        self.db = db
        self.family_id = family_id

    def resolve_targets(
        self, *, assignee_member_id: UUID | None, car_ids: list[UUID]
    ) -> list[EventTargetPlan]:
        if assignee_member_id is not None:
            member = (
                self.db.query(Member)
                .filter(
                    Member.id == assignee_member_id,
                    Member.family_id == self.family_id,
                )
                .first()
            )
            if not member:
                return []
            return [self._plan_for(member)]

        # No assignee — fan out to every active member.
        members = (
            self.db.query(Member)
            .filter(
                Member.family_id == self.family_id,
                Member.status == MemberStatus.active,
            )
            .all()
        )
        return [self._plan_for(m) for m in members]

    def _plan_for(self, member: Member) -> EventTargetPlan:
        token = (
            self.db.query(GoogleToken)
            .filter(GoogleToken.member_id == member.id)
            .first()
        )
        if not token or token.status != GoogleTokenStatus.connected:
            return EventTargetPlan(
                member_id=member.id, skipped_reason="no_google_connection"
            )
        return EventTargetPlan(member_id=member.id, skipped_reason=None)
