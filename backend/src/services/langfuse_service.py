"""
Langfuse v3 integration.

The v3 Python SDK uses a single global client configured once at startup.
After `LangfuseService.initialize(settings)`, any module can call
`get_client()` or use `@observe` decorators — they all share this instance.
"""
from langfuse import Langfuse, get_client

from src.core.settings import Settings
from src.services.logger import get_logger

logger = get_logger("langfuse_service")


class LangfuseService:
    _initialized: bool = False

    @classmethod
    def initialize(cls, settings: Settings) -> None:
        if cls._initialized:
            return

        # Constructing Langfuse() registers it as the process-wide singleton;
        # later `get_client()` calls return this same instance.
        Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            tracing_enabled=settings.LANGFUSE_ENABLED,
        )

        if settings.LANGFUSE_ENABLED:
            try:
                get_client().auth_check()
                logger.info("Langfuse v3 client authenticated against %s", settings.LANGFUSE_HOST)
            except Exception as e:
                logger.warning("Langfuse auth_check failed (continuing without tracing): %s", e)

        cls._initialized = True

    @classmethod
    def get_langfuse(cls) -> Langfuse:
        if not cls._initialized:
            raise RuntimeError("LangfuseService not initialized. Call initialize() first.")
        return get_client()
