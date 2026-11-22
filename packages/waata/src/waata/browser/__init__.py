"""Browser interfaces and Playwright integration."""

from typing import Protocol


class BrowserAdapter(Protocol):
    """Injection boundary; C3 operations will be added in W03-W05."""
