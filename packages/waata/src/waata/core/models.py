"""Small, domain-independent validation primitives for public contracts."""

from datetime import datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
)

_HTTP_URL = TypeAdapter(AnyHttpUrl)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


def non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def http_url(value: str) -> str:
    """Validate syntax only; execution authorization belongs to C3."""
    try:
        _HTTP_URL.validate_python(value)
        parsed = urlsplit(value)
        port = parsed.port
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and (port is None or port > 0)
            and not any(c.isspace() or ord(c) < 32 for c in value)
            and "\\" not in value
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("must be an absolute HTTP(S) URL without credentials")
    return value


def utc_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("must be an ISO 8601 UTC timestamp") from None
    if "T" not in value or parsed.utcoffset() != timedelta(0):
        raise ValueError("must be an ISO 8601 UTC timestamp")
    return value


NonBlank = Annotated[str, AfterValidator(non_blank)]
HttpURL = Annotated[str, AfterValidator(http_url)]
UTCTimestamp = Annotated[str, AfterValidator(utc_timestamp)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveFloat = Annotated[float, Field(gt=0)]
