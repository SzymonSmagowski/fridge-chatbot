"""Member CRUD scoped to one family. Joins the google_tokens row to expose a
single `google` field on the response."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models import GoogleToken, GoogleTokenStatus, Member, MemberStatus
from src.schemas.members import (
    GoogleState,
    MemberCreateRequest,
    MemberResponse,
    MemberUpdateRequest,
)

MemberStatusFilter = Literal["active", "inactive", "all"]


class MemberService:
    def __init__(self, db: Session, family_id: UUID) -> None:
        self.db = db
        self.family_id = family_id

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

    def create(self, data: MemberCreateRequest) -> Member:
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
        return member

    def update(self, member_id: UUID, data: MemberUpdateRequest) -> Member:
        member = self.get(member_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(member, field, value)
        self.db.commit()
        self.db.refresh(member)
        return member

    def set_status(self, member_id: UUID, status: MemberStatus) -> Member:
        member = self.get(member_id)
        member.status = status
        self.db.commit()
        self.db.refresh(member)
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
