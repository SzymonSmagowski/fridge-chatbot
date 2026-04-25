from langchain_openai import ChatOpenAI

from src.core.settings import Settings


class LLMFactory:
    @staticmethod
    def create_llm(settings: Settings, **kwargs):
        """Build a Chat LLM instance backed by OpenAI."""
        return ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model=settings.DEFAULT_MODEL,
            **kwargs,
        )
