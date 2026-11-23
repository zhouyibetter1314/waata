"""Target scope and fixture credentials for controlled browser tests (NFR-004)."""

import ipaddress
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from html import escape
from urllib.parse import quote, quote_plus, urlsplit

from pydantic import TypeAdapter

from .models import LocatorSpec

LOCATOR_ADAPTER = TypeAdapter(LocatorSpec)


def normalized_host(value: str) -> str:
    value = value.rstrip(".")
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        host = value.encode("idna").decode("ascii").lower()
        if not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*", host):
            raise ValueError("invalid browser hostname") from None
        # Chromium accepts alternate numeric IP syntax. Use canonical IP literals.
        if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", host.rsplit(".", 1)[-1]):
            raise ValueError("browser IP literals must use canonical syntax") from None
        return host


@dataclass(frozen=True)
class Origin:
    scheme: str
    host: str
    port: int

    @classmethod
    def from_url(cls, value: str) -> "Origin":
        if "\\" in value or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError("invalid browser target URL")
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError("browser target must be an absolute HTTP(S) URL")
        port = parts.port
        if port == 0:
            raise ValueError("invalid browser port")
        return cls(
            scheme=parts.scheme,
            host=normalized_host(parts.hostname),
            port=port or (443 if parts.scheme == "https" else 80),
        )

    def permits(self, value: str) -> bool:
        try:
            return self == Origin.from_url(value)
        except ValueError:
            return False

    def permits_websocket(self, value: str, allowed_paths: frozenset[str]) -> bool:
        scheme, separator, rest = value.partition(":")
        http_scheme = {"ws": "http", "wss": "https"}.get(scheme)
        if not separator or http_scheme is None:
            return False
        target = f"{http_scheme}:{rest}"
        return self.permits(target) and urlsplit(target).path in allowed_paths


@dataclass(frozen=True)
class CredentialField:
    """A caller-provided test secret and its permitted input locator."""

    value: str = field(repr=False)
    locator: LocatorSpec | dict[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("fixture credential must have a non-empty value")
        locator = LOCATOR_ADAPTER.validate_python(self.locator, strict=True)
        object.__setattr__(self, "locator", locator)


def redactions(fields: dict[str, CredentialField]) -> tuple[str, ...]:
    return redaction_variants(set(fields) | {field.value for field in fields.values()})


def redaction_variants(markers: Iterable[str]) -> tuple[str, ...]:
    variants = {
        variant
        for marker in markers
        for variant in (
            marker,
            quote(marker, safe=""),
            quote_plus(marker),
            escape(marker),
            json.dumps(marker, ensure_ascii=False)[1:-1],
        )
    }
    return tuple(sorted(variants, key=len, reverse=True))


def sanitize(value: str, markers: tuple[str, ...]) -> str:
    for marker in markers:
        value = value.replace(marker, "[redacted]")
    return value


def safe_url(value: str, markers: tuple[str, ...]) -> str:
    parts = urlsplit(value)
    # Query strings and fragments can contain credentials or session identifiers.
    return sanitize(parts._replace(query="", fragment="").geturl(), markers)
