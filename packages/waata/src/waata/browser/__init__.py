"""Interfaces and Playwright integration for controlled browser tests."""

from .adapter import (
    BrowserAdapter,
    BrowserLimits,
    BrowserSession,
    BrowserSetupCleanupError,
    PlaywrightAdapter,
)
from .fake import FakeBrowserAdapter
from .models import InspectArgs, LocatorSpec
from .policy import CredentialField

__all__ = [
    "BrowserAdapter",
    "BrowserLimits",
    "BrowserSession",
    "BrowserSetupCleanupError",
    "CredentialField",
    "FakeBrowserAdapter",
    "InspectArgs",
    "LocatorSpec",
    "PlaywrightAdapter",
]
