"""ChatStreamer: pub/sub fanout for chat tokens + family broadcasts (§7.7).

Producers (LangGraph nodes, mutating route handlers) call publish_token /
publish_family_event. Subscribers (the WS handler) hold a context-managed
pubsub for the lifetime of a connection.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.core.pubsub import family_events_channel, thread_tokens_channel
from src.services.logger import get_logger

logger = get_logger("chat_streaming")


class ChatStreamer:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def publish_token(self, thread_id: Any, chunk: dict) -> None:
        await self._publish(thread_tokens_channel(thread_id), chunk)

    async def publish_family_event(self, family_id: Any, payload: dict) -> None:
        await self._publish(family_events_channel(family_id), payload)

    async def _publish(self, channel: str, payload: dict) -> None:
        try:
            await self.redis.publish(channel, json.dumps(payload, default=str))
        except RedisError as exc:
            logger.warning("publish failed on %s: %s", channel, exc)

    @asynccontextmanager
    async def subscribe_thread(
        self, thread_id: Any
    ) -> AsyncIterator["PubSubChannel"]:
        async with self._subscribe(thread_tokens_channel(thread_id)) as channel:
            yield channel

    @asynccontextmanager
    async def subscribe_family(
        self, family_id: Any
    ) -> AsyncIterator["PubSubChannel"]:
        async with self._subscribe(family_events_channel(family_id)) as channel:
            yield channel

    @asynccontextmanager
    async def _subscribe(self, channel_name: str) -> AsyncIterator["PubSubChannel"]:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel_name)
        try:
            yield PubSubChannel(pubsub, channel_name)
        finally:
            try:
                await pubsub.unsubscribe(channel_name)
                await pubsub.close()
            except RedisError:
                pass


class PubSubChannel:
    """Thin async iterator over JSON messages on a single channel."""

    def __init__(self, pubsub, name: str) -> None:
        self.pubsub = pubsub
        self.name = name

    async def listen(self) -> AsyncIterator[dict]:
        async for raw in self.pubsub.listen():
            if raw is None:
                continue
            if raw.get("type") != "message":
                continue
            data = raw.get("data")
            if data is None:
                continue
            try:
                yield json.loads(data)
            except (TypeError, ValueError):
                continue
