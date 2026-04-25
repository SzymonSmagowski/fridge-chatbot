"""GoogleTokenService — load encrypted refresh token, refresh access token,
cache the access token in Redis (TTL = expires_in - 120s).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from src.core.settings import Settings
from src.models import GoogleToken, GoogleTokenStatus
from src.services.crypto_service import CryptoService
from src.services.logger import get_logger

logger = get_logger("google_token")

ACCESS_TOKEN_KEY = "google:access_token:{member_id}"
ACCESS_TOKEN_DEFAULT_TTL = 3300  # ~55 min — Google access tokens last 1h


class GoogleTokenService:
    def __init__(
        self,
        settings: Settings,
        db: Session,
        redis: Redis,
        crypto: CryptoService,
    ) -> None:
        self.settings = settings
        self.db = db
        self.redis = redis
        self.crypto = crypto

    def load(self, member_id: UUID) -> GoogleToken | None:
        return self.db.query(GoogleToken).filter(GoogleToken.member_id == member_id).first()

    async def get_access_token(self, member_id: UUID) -> str | None:
        """Return a valid access token (cached or freshly refreshed). None if
        the member has no Google connection or the refresh fails."""
        cache_key = ACCESS_TOKEN_KEY.format(member_id=member_id)
        try:
            cached = await self.redis.get(cache_key)
        except RedisError:
            cached = None
        if cached:
            return cached

        token_row = self.load(member_id)
        if not token_row or token_row.status == GoogleTokenStatus.revoked:
            return None

        refreshed = await self._refresh(token_row)
        if refreshed is None:
            return None

        access_token, expires_in = refreshed
        ttl = max(60, expires_in - 120)
        try:
            await self.redis.set(cache_key, access_token, ex=ttl)
        except RedisError as exc:
            logger.warning("cache set google access token failed: %s", exc)
        return access_token

    async def _refresh(self, row: GoogleToken) -> tuple[str, int] | None:
        if not self.settings.GOOGLE_CLIENT_ID or not self.settings.GOOGLE_CLIENT_SECRET:
            logger.warning("google client_id/secret not configured; cannot refresh")
            return None

        try:
            refresh_token = self.crypto.decrypt(row.refresh_token_encrypted)
        except ValueError:
            logger.error("failed to decrypt refresh token for member %s", row.member_id)
            row.status = GoogleTokenStatus.reconnect_needed
            self.db.commit()
            return None

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": self.settings.GOOGLE_CLIENT_ID,
                        "client_secret": self.settings.GOOGLE_CLIENT_SECRET,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                )
            except httpx.HTTPError as exc:
                logger.warning("refresh request failed: %s", exc)
                return None

        if resp.status_code != 200:
            logger.warning(
                "google token refresh returned %s for member %s",
                resp.status_code, row.member_id,
            )
            if resp.status_code in (400, 401):
                row.status = GoogleTokenStatus.reconnect_needed
                self.db.commit()
            return None

        data = resp.json()
        row.last_refreshed_at = datetime.utcnow()
        row.status = GoogleTokenStatus.connected
        self.db.commit()
        return data["access_token"], int(data.get("expires_in", ACCESS_TOKEN_DEFAULT_TTL))

    def store(
        self,
        member_id: UUID,
        refresh_token: str,
        google_sub: str,
        google_email: str,
        scope: str,
    ) -> GoogleToken:
        """Upsert a member's encrypted refresh token."""
        encrypted = self.crypto.encrypt(refresh_token)
        existing = self.load(member_id)
        if existing:
            existing.refresh_token_encrypted = encrypted
            existing.google_sub = google_sub
            existing.google_email = google_email
            existing.scope = scope
            existing.status = GoogleTokenStatus.connected
            existing.last_refreshed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing

        row = GoogleToken(
            member_id=member_id,
            refresh_token_encrypted=encrypted,
            google_sub=google_sub,
            google_email=google_email,
            scope=scope,
            status=GoogleTokenStatus.connected,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
