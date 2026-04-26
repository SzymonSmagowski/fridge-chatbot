"""Request-scoped actor context for service-layer publishes (§6.6).

Services that publish `family:{id}:events` frames stamp the broadcast with
`actor=current_actor.get()`. The default `"rest"` covers the common case;
LangGraph tool nodes override to `"chat-tool"` before invoking a service.
Workers do NOT use this — they pass `actor="sync-worker"` explicitly to
`ChatStreamer.publish_family_event`.

ContextVars are async-safe: each `asyncio.Task` inherits a copy of the
current context, so concurrent requests/tools never bleed actor values.
"""
from __future__ import annotations

from contextvars import ContextVar

current_actor: ContextVar[str] = ContextVar("current_actor", default="rest")
