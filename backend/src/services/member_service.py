"""Member CRUD scoped to one family. Joins the google_tokens row to expose a
single `google` field on the response."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.context import current_actor
from src.core.family_events import family_event_payload
from src.models import GoogleToken, GoogleTokenStatus, Member, MemberStatus
from src.schemas.members import (
    GoogleState,
    MemberCreateRequest,
    MemberResponse,
    MemberUpdateRequest,
)
from src.services.chat_streaming import ChatStreamer

MemberStatusFilter = Literal["active", "inactive", "all"]


class MemberService:
    def __init__(
        self, db: Session, family_id: UUID, streamer: ChatStreamer
    ) -> None:
        self.db = db
        self.family_id = family_id
        self.streamer = streamer

    async def _publish(self, *, type: str, member_id: UUID) -> None:
        await self.streamer.publish_family_event(
            self.family_id,
            family_event_payload(
                type=type,
                entity="members",
                id=member_id,
                actor=current_actor.get(),
            ),
        )

    def list(self, status_filter: MemberStatusFilter = "active") -> list[Member]:
        q = self.db.query(Member).filter(Member.family_id == self.family_id)
        if status_filter == "active":
            q = q.filter(Member.status == MemberStatus.active)
        elif status_filter == "inactive":
            q = q.filter(Member.status == MemberStatus.inactive)
        return q.order_by(Member.created_at.asc()).all()

    def get(self, member_id: UUID) -> Member:
        member = (
            self.db.query(Member)
            .filter(Member.id == member_id, Member.family_id == self.family_id)
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=404,
                detail={"code": "members.not_found", "detail": "Member not found"},
            )
        return member

    async def create(self, data: MemberCreateRequest) -> Member:
        member = Member(
            family_id=self.family_id,
            name=data.name,
            nickname=data.nickname,
            color=data.color,
            status=MemberStatus.active,
            is_setup_owner=False,
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        await self._publish(type="member.created", member_id=member.id)
        return member

    async def update(self, member_id: UUID, data: MemberUpdateRequest) -> Member:
        member = self.get(member_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(member, field, value)
        self.db.commit()
        self.db.refresh(member)
        await self._publish(type="member.updated", member_id=member.id)
        return member

    async def set_status(self, member_id: UUID, status: MemberStatus) -> Member:
        member = self.get(member_id)
        member.status = status
        self.db.commit()
        self.db.refresh(member)
        type_name = (
            "member.set-active"
            if status == MemberStatus.active
            else "member.set-inactive"
        )
        await self._publish(type=type_name, member_id=member.id)
        return member

    def google_state(self, member: Member) -> GoogleState:
        token: GoogleToken | None = (
            self.db.query(GoogleToken)
            .filter(GoogleToken.member_id == member.id)
            .first()
        )
        if not token:
            return GoogleState(status="not_connected", email=None, connected_at=None)
        if token.status == GoogleTokenStatus.revoked:
            return GoogleState(status="revoked", email=None, connected_at=token.connected_at)
        return GoogleState(
            status=token.status.value,
            email=token.google_email,
            connected_at=token.connected_at,
        )

    def to_response(self, member: Member) -> MemberResponse:
        return MemberResponse(
            id=member.id,
            family_id=member.family_id,
            name=member.name,
            nickname=member.nickname,
            color=member.color,
            status=member.status.value,
            is_setup_owner=member.is_setup_owner,
            google=self.google_state(member),
            created_at=member.created_at,
        )
