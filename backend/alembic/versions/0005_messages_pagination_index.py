"""composite index on messages for cursor-paginated history

Revision ID: 0005_messages_pagination_index
Revises: 0004_voice_locale
Create Date: 2026-05-10

The chat history pagination contract (design A.1) needs `(thread_id,
created_at DESC, message_id DESC)` covered by an index so the cursor lookup
is index-only. Today `messages` only indexes `thread_id`; with a few hundred
messages per thread the per-page filter is fine, but the order-by has to
sort in memory. Add a composite ordered index up front so the planner can
walk it and stop after `limit + 1` rows.

The `message_id` (UUID) tiebreaker is needed because two messages can share
a microsecond `created_at` — fixtures hit this; production rarely does. The
column is already unique; including it in the index just lets the planner
emit a stable, total-ordered scan.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005_messages_pagination_index"
down_revision: Union[str, Sequence[str], None] = "0004_voice_locale"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_messages_thread_created_id "
        "ON messages (thread_id, created_at DESC, message_id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_thread_created_id")
