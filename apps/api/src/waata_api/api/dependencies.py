"""Resolve authenticated API callers at the HTTP trust boundary."""

from dataclasses import dataclass
from hmac import compare_digest
from ipaddress import ip_address
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from waata_api.api.errors import ApiError

if TYPE_CHECKING:
    from waata_api.infrastructure.artifacts import FileArtifactStore
    from waata_api.infrastructure.config import Settings
    from waata_api.repositories import PostgresRepository


@dataclass(frozen=True)
class ApiRuntime:
    settings: "Settings"
    repository: "PostgresRepository"
    artifact_store: "FileArtifactStore"


def get_runtime(request: Request) -> ApiRuntime:
    return request.app.state.runtime


Runtime = Annotated[ApiRuntime, Depends(get_runtime)]


def _is_loopback(host: str) -> bool:
    try:
        address = ip_address(host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_loopback or (mapped is not None and mapped.is_loopback)


def get_owner(request: Request, runtime: Runtime) -> str:
    settings = runtime.settings
    hosts = request.headers.getlist("host")
    if len(hosts) != 1 or hosts[0].lower() not in settings.allowed_hosts:
        raise ApiError("UNAUTHENTICATED")
    origin = request.headers.get("origin")
    if settings.auth_mode == "local":
        if request.client is None or not _is_loopback(request.client.host):
            raise ApiError("UNAUTHENTICATED")
        owner = settings.local_owner_id
    elif settings.auth_mode == "gateway":
        tokens = request.headers.getlist("x-waata-gateway-token")
        principals = request.headers.getlist("x-waata-principal")
        if len(tokens) != 1 or len(principals) != 1:
            raise ApiError("UNAUTHENTICATED")
        owner = principals[0]
        if (
            not settings.gateway_token
            or not compare_digest(tokens[0].encode(), settings.gateway_token.encode())
            or not owner
            or len(owner) > 256
            or any(not char.isascii() or not char.isprintable() for char in owner)
            or owner.strip() != owner
        ):
            raise ApiError("UNAUTHENTICATED")
    else:
        raise ApiError("UNAUTHENTICATED")
    if request.method in {"POST", "DELETE"} and (
        (origin is None and settings.auth_mode != "local")
        or (origin is not None and origin not in settings.web_origins)
    ):
        raise ApiError("INVALID_REQUEST")
    return owner


Owner = Annotated[str, Depends(get_owner)]
