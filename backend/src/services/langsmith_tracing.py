from src.core.settings import Settings
from src.services.logger import get_logger

logger = get_logger("langsmith_tracing")


class LangSmithTracing:
    _settings: Settings | None = None
    _initialized: bool = False

    @classmethod
    def initialize(cls, settings: Settings) -> None:
        if cls._initialized:
            return
        cls._settings = settings
        cls._initialized = True
        if str(settings.LANGCHAIN_TRACING_V2).lower() != "true":
            logger.debug("LangSmith tracing disabled")
