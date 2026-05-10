"""Periodic thread compaction.

Long chats that replay verbatim into every LLM call hit two problems:
1. Context-window cost grows linearly — by message #80, every reply pays for
   re-reading messages #1–60 that have nothing to do with what was just said.
2. The LLM gets distracted by ancient context, which degrades reply quality.

We solve both with a rolling summary: the oldest messages are folded into a
single natural-language summary stored on `threads.summary`, and only the
last `WINDOW_SIZE` messages are replayed verbatim. The summary is regenerated
every `REGENERATE_EVERY` new messages once the thread crosses the threshold,
so summarization cost is amortized — not paid on every turn.

Trade-offs (recorded so future-you knows what you bought):
- The summary loses verbatim quotes. If a user 30 turns later asks "what was
  the dish you suggested last week", the LLM paraphrases. Acceptable for a
  household kiosk where conversations are short and event-driven.
- A summary regeneration is itself an LLM call. We trigger it after the
  user's reply has streamed (post-`save_message`), so the user never waits
  on the summarization round-trip — it runs in the background.
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from src.core.settings import Settings
from src.models.database import Message, Thread
from src.services.llm_factory import LLMFactory
from src.services.logger import get_logger

logger = get_logger("thread_summary_service")

# Number of recent messages always replayed verbatim into the LLM context.
WINDOW_SIZE = 20
# How many messages must accrue beyond the window before we regenerate the
# summary. Higher = lower cost, more drift; lower = fresher summary, more
# LLM round-trips. 10 means roughly one summarization every ~5 user turns
# once the thread is "long".
REGENERATE_EVERY = 10
# Soft cap on summary text length — keep it short enough that adding it as a
# system message doesn't itself blow context budgets on a busy day.
MAX_SUMMARY_CHARS = 2_000


_SUMMARIZE_PROMPT = (
    "You are summarizing the earlier part of a conversation between a "
    "household member and the fridge assistant. Write a concise summary "
    "(under {max_chars} characters) capturing: who said what was important, "
    "any decisions made, any in-flight intents (notes pending, events "
    "awaiting a date, etc.), and any preferences the user expressed. Skip "
    "small talk. Skip pleasantries. Reply in the user's language.\n\n"
    "{prior_summary}"
    "Recent exchange to fold in:\n{transcript}\n\n"
    "Summary:"
)


def _format_transcript(messages: List[Message]) -> str:
    lines: list[str] = []
    for m in messages:
        prefix = m.role.upper()
        lines.append(f"{prefix}: {m.content}")
    return "\n".join(lines)


async def maybe_summarize_thread(
    db: Session,
    thread_uuid: UUID,
    settings: Settings,
) -> bool:
    """Regenerate the thread's running summary if enough new messages have
    accumulated since the last summarization. Returns True if a summary was
    written (caller can use this for telemetry); False if the thread is still
    under threshold or already up-to-date.

    Safe to call after every assistant reply — it's a no-op until the thread
    grows past `WINDOW_SIZE + REGENERATE_EVERY`.
    """
    thread = db.query(Thread).filter(Thread.thread_id == thread_uuid).first()
    if thread is None:
        return False

    all_messages = (
        db.query(Message)
        .filter(Message.thread_id == thread_uuid)
        .order_by(Message.id.asc())
        .all()
    )
    if len(all_messages) <= WINDOW_SIZE + REGENERATE_EVERY:
        return False

    # Everything except the last WINDOW_SIZE goes into the summary.
    to_summarize = all_messages[:-WINDOW_SIZE]
    new_anchor_id = to_summarize[-1].id

    # If we already summarized through this exact id (or further), skip.
    prior_anchor = thread.summary_through_message_id or 0
    if new_anchor_id - prior_anchor < REGENERATE_EVERY:
        return False

    # Only fold in the messages that are NEW since the last summary — the
    # prior summary already captures everything before that anchor.
    new_messages = [m for m in to_summarize if m.id > prior_anchor]
    if not new_messages:
        return False

    transcript = _format_transcript(new_messages)
    prior_summary_block = (
        f"Prior summary so far:\n{thread.summary}\n\n" if thread.summary else ""
    )
    prompt = _SUMMARIZE_PROMPT.format(
        max_chars=MAX_SUMMARY_CHARS,
        prior_summary=prior_summary_block,
        transcript=transcript,
    )

    # Use the same LLM as the chat path; temperature 0 for stable summaries.
    llm = LLMFactory.create_llm(settings, temperature=0.0)
    response = await llm.ainvoke([SystemMessage(content=prompt)])
    summary_text = (response.content or "").strip()
    if not summary_text:
        logger.warning(
            "thread %s summarization returned empty content; skipping write",
            thread_uuid,
        )
        return False

    # Truncate hard if the model overshoots the soft cap. Better a clipped
    # summary than a context-blown one.
    if len(summary_text) > MAX_SUMMARY_CHARS:
        summary_text = summary_text[: MAX_SUMMARY_CHARS - 1] + "…"

    thread.summary = summary_text
    thread.summary_through_message_id = new_anchor_id
    db.commit()
    logger.info(
        "thread %s summary regenerated through message_id=%s (%d chars)",
        thread_uuid,
        new_anchor_id,
        len(summary_text),
    )
    return True


def load_compacted_history(
    db: Session,
    thread_uuid: UUID,
    *,
    exclude_last: bool = True,
) -> list:
    """Return the LLM history for `thread_uuid` as a list of langchain
    messages: optional summary `SystemMessage` first, then up to `WINDOW_SIZE`
    most recent verbatim messages.

    `exclude_last=True` (default) drops the very latest message — used by
    `ParentRouter` so the just-saved user message isn't double-counted (it's
    passed separately to `assistant.astream()`).
    """
    thread = db.query(Thread).filter(Thread.thread_id == thread_uuid).first()
    if thread is None:
        return []

    q = db.query(Message).filter(Message.thread_id == thread_uuid)
    if thread.summary_through_message_id:
        q = q.filter(Message.id > thread.summary_through_message_id)
    rows = q.order_by(Message.id.asc()).all()

    if exclude_last and rows:
        rows = rows[:-1]
    rows = rows[-WINDOW_SIZE:]

    history: list = []
    if thread.summary:
        history.append(
            SystemMessage(
                content=(
                    "Summary of earlier conversation in this thread "
                    "(use as background context only, do not quote verbatim):\n"
                    f"{thread.summary}"
                )
            )
        )
    for r in rows:
        if r.role == "user":
            history.append(HumanMessage(content=r.content))
        elif r.role == "assistant":
            history.append(AIMessage(content=r.content))
    return history
