"""Interfaces and Playwright integration for controlled browser tests."""

from .adapter import (
    BrowserAdapter,
    BrowserLimits,
    BrowserSession,
    BrowserSetupCleanupError,
    PlaywrightAdapter,
)
from .models import InspectArgs, LocatorSpec
from .policy import CredentialField

__all__ = [
    "BrowserAdapter",
    "BrowserLimits",
    "BrowserSession",
    "BrowserSetupCleanupError",
    "CredentialField",
    "InspectArgs",
    "LocatorSpec",
    "PlaywrightAdapter",
]
