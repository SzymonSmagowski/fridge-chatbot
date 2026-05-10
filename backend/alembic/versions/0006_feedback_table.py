"""feedback table + 3 enums (feedback_category, feedback_author_kind, feedback_status)

Revision ID: 0006_feedback_table
Revises: 0005_messages_pagination_index
Create Date: 2026-05-10

Adds the `feedback` table and its 3 supporting enums (design §B.1, §B.2).
Two indexes on the table:
- `ix_feedback_family_created` — primary read pattern (timeline scroll).
- `ix_feedback_family_status` — supports status filtering on the list page.

Enums must be created BEFORE the table since Postgres ENUM is a first-class
type. Down-migration drops the table THEN the enums (reverse order) for the
same reason.

All FKs except `family_id` are nullable: kiosk submissions have no logged-in
member; future web-portal submissions may have no device; assistant
submissions don't always carry a thread_id. `family_id` is mandatory because
the feedback channel is family-scoped end-to-end.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_feedback_table"
down_revision: Union[str, Sequence[str], None] = "0005_messages_pagination_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FEEDBACK_CATEGORY_VALUES = ("bug", "improvement", "question", "other")
_FEEDBACK_AUTHOR_KIND_VALUES = ("user", "assistant_on_behalf_of_user")
_FEEDBACK_STATUS_VALUES = ("open", "reviewing", "resolved")


def upgrade() -> None:
    bind = op.get_bind()

    feedback_category = postgresql.ENUM(
        *_FEEDBACK_CATEGORY_VALUES,
        name="feedback_category",
        create_type=False,
    )
    feedback_author_kind = postgresql.ENUM(
        *_FEEDBACK_AUTHOR_KIND_VALUES,
        name="feedback_author_kind",
        create_type=False,
    )
    feedback_status = postgresql.ENUM(
        *_FEEDBACK_STATUS_VALUES,
        name="feedback_status",
        create_type=False,
    )
    feedback_category.create(bind, checkfirst=True)
    feedback_author_kind.create(bind, checkfirst=True)
    feedback_status.create(bind, checkfirst=True)

    op.create_table(
        "feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("threads.thread_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "category",
            postgresql.ENUM(
                *_FEEDBACK_CATEGORY_VALUES,
                name="feedback_category",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "author_kind",
            postgresql.ENUM(
                *_FEEDBACK_AUTHOR_KIND_VALUES,
                name="feedback_author_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                *_FEEDBACK_STATUS_VALUES,
                name="feedback_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_feedback_family_id", "feedback", ["family_id"]
    )
    op.create_index(
        "ix_feedback_family_created",
        "feedback",
        ["family_id", "created_at"],
    )
    op.create_index(
        "ix_feedback_family_status",
        "feedback",
        ["family_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_family_status", table_name="feedback")
    op.drop_index("ix_feedback_family_created", table_name="feedback")
    op.drop_index("ix_feedback_family_id", table_name="feedback")
    op.drop_table("feedback")

    bind = op.get_bind()
    for enum_name in (
        "feedback_status",
        "feedback_author_kind",
        "feedback_category",
    ):
        bind.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
