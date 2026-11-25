"""Language model interfaces and adapters."""

from waata.core.model import LLMProvider
from waata.llm.openai_like import OpenAILike

__all__ = ["LLMProvider", "OpenAILike"]
