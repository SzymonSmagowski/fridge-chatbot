"""Google OAuth: build authorize URLs, exchange codes, revoke tokens.

Wraps `google_auth_oauthlib` so callers don't import that package directly.
"""
from __future__ import annotations

from typing import Any

import httpx
from google_auth_oauthlib.flow import Flow

from src.core.settings import Settings
from src.services.logger import get_logger

logger = get_logger("google_oauth")


class GoogleOAuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _client_config(self) -> dict[str, Any]:
        if not self.settings.GOOGLE_CLIENT_ID or not self.settings.GOOGLE_CLIENT_SECRET:
            raise RuntimeError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured"
            )
        return {
            "web": {
                "client_id": self.settings.GOOGLE_CLIENT_ID,
                "client_secret": self.settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.settings.GOOGLE_OAUTH_REDIRECT_URI],
            }
        }

    def build_authorize_url(self, state: str) -> str:
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=self.settings.GOOGLE_OAUTH_SCOPES_LIST,
            redirect_uri=self.settings.GOOGLE_OAUTH_REDIRECT_URI,
        )
        url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return url

    def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for tokens.

        Returns a dict with: access_token, refresh_token, scope, expires_in,
        id_token (decoded subset: sub, email, name, given_name).
        """
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=self.settings.GOOGLE_OAUTH_SCOPES_LIST,
            redirect_uri=self.settings.GOOGLE_OAUTH_REDIRECT_URI,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        id_info = self._decode_id_token(getattr(creds, "id_token", None))
        return {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "scope": " ".join(creds.scopes or []),
            "expires_in": int(
                (creds.expiry - creds._helpers_now()).total_seconds()  # type: ignore[attr-defined]
            )
            if getattr(creds, "expiry", None)
            else 3600,
            "google_sub": id_info.get("sub"),
            "google_email": id_info.get("email"),
            "google_name": id_info.get("name"),
            "google_given_name": id_info.get("given_name"),
        }

    @staticmethod
    def _decode_id_token(id_token: str | None) -> dict[str, Any]:
        """Verify and decode the id_token payload via Google's tokeninfo endpoint.

        Avoids pulling in google.oauth2.id_token (which needs a request transport).
        Acceptable for v1 — id_token verification happens once per pairing.
        """
        if not id_token:
            return {}
        try:
            resp = httpx.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return {}
            return resp.json()
        except Exception as exc:  # noqa: BLE001 — best-effort decode
            logger.warning("id_token decode failed: %s", exc)
            return {}

    async def revoke(self, token: str) -> bool:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                return resp.status_code in (200, 400)
            except httpx.HTTPError as exc:
                logger.warning("revoke failed: %s", exc)
                return False
