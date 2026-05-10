"""threads.summary + summary_through_message_id for periodic compaction

Revision ID: 0003_thread_summary
Revises: 0002_event_parent_id
Create Date: 2026-05-09

Adds two columns to `threads` so long chats can be compacted into a running
summary instead of replaying the entire history into the LLM context window:

- `summary` (TEXT, nullable) — natural-language compaction of all messages up
  to and including `summary_through_message_id`.
- `summary_through_message_id` (INTEGER, nullable) — the `messages.id` (NOT
  `message_id` UUID — the auto-increment integer PK) of the last message
  included in the current summary. New messages with `id` greater than this
  are appended verbatim to the LLM context until the next summarization
  pass triggers.

`ParentRouter._load_history` reads both: it returns
`[SystemMessage(summary)] + messages_after_anchor[-WINDOW:]` (20 message
window), and `maybe_summarize_thread` regenerates the summary every 10 new
messages once the thread has crossed `WINDOW + REGENERATE_EVERY` total.

Both columns are nullable so existing threads continue to work uncompacted —
the summary materializes lazily on the next message after the threshold.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_thread_summary"
down_revision: Union[str, Sequence[str], None] = "0002_event_parent_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "threads",
        sa.Column("summary_through_message_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("threads", "summary_through_message_id")
    op.drop_column("threads", "summary")
