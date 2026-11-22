"""Run observers and trace integration."""

from typing import Protocol


class Observer(Protocol):
    """Optional caller-owned tracing boundary; no operations are required by W01."""
