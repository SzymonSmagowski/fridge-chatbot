"""Redis pub/sub channel name helpers.

The actual publish + subscribe wrappers live in `services/chat_streaming.py` so
they can hold async iterator state and cleanly handle subscription lifecycle.
This module is just constants + small key builders so callers don't typo
channel names.
"""
from __future__ import annotations

from typing import Any


def thread_tokens_channel(thread_id: Any) -> str:
    return f"thread:{thread_id}:tokens"


def family_events_channel(family_id: Any) -> str:
    return f"family:{family_id}:events"
