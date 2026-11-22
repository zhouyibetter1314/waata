"""Language model interfaces and adapters."""

from waata.core.model import LLMProvider
from waata.llm.fake import FakeLLM
from waata.llm.openai_like import OpenAILike

__all__ = ["FakeLLM", "LLMProvider", "OpenAILike"]
