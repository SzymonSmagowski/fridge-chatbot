from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from src.core.settings import Settings
from src.core.dependencies import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    if not settings.BACKEND_DEBUG_API_KEY or api_key != settings.BACKEND_DEBUG_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
