from src.core.settings import Settings
from src.services.llm_factory import LLMFactory
from src.services.logger import get_logger

logger = get_logger("llm_utils")


class LLMUtilsService:
    def __init__(self, settings: Settings):
        self.model = LLMFactory.create_llm(settings, temperature=settings.DEFAULT_TEMPERATURE)

    async def generate_thread_title(self, user_message: str) -> str:
        """Generate a concise title (≤ 6 words) from the first user message."""
        prompt = (
            "Based on this message, create a very concise title (max 6 words) "
            "that captures the main topic. Title should be clear and descriptive. "
            f"Message: {user_message}"
        )
        try:
            response = await self.model.ainvoke([{"role": "user", "content": prompt}])
            title = response.content.strip().replace('"', "").replace("'", "")
            return title[:200]
        except Exception as e:
            logger.error("Error generating thread title: %s", e, exc_info=True)
            return "New conversation"
