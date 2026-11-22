"""Language model interfaces and adapters."""

from typing import Protocol


class LLMProvider(Protocol):
    """Injection boundary; model operations will be specified in W02."""
