"""Frame committed C4 events for SSE replay and live following."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC
from time import monotonic

from fastapi.encoders import jsonable_encoder
from psycopg import InterfaceError, OperationalError

from waata_api.api.dependencies import ApiRuntime
from waata_api.api.errors import ApiError

TERMINAL_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled"})
_CURSOR = re.compile(r"[0-9]+")
_LOG = logging.getLogger(__name__)


def event_cursor(header: str | None, query: str | None, *, head: int) -> int:
    raw = header or ("0" if query is None else query)
    if _CURSOR.fullmatch(raw) is None:
        raise ApiError("INVALID_EVENT_CURSOR")
    significant_digits = raw.lstrip("0") or "0"
    if (
        len(significant_digits) > len(str(head))
        or (cursor := int(significant_digits)) > head
    ):
        raise ApiError("INVALID_EVENT_CURSOR")
    return cursor


async def stream_events(
    runtime: ApiRuntime, run_id: str, cursor: int, *, request_id: str
) -> AsyncIterator[str]:
    keepalive = runtime.settings.sse_keepalive_seconds
    poll_interval = runtime.settings.sse_poll_seconds
    last_signal = monotonic()
    while True:
        try:
            events = await runtime.repository.read_events(run_id, after=cursor)
        except (InterfaceError, OperationalError):
            _LOG.warning("SSE storage unavailable request_id=%s", request_id)
            return
        for event in events:
            cursor = event["sequence"]
            name = event["type"]
            published = {**event, "timestamp": event["timestamp"].astimezone(UTC)}
            data = json.dumps(jsonable_encoder(published), ensure_ascii=False)
            yield f"id: {cursor}\nevent: {name}\ndata: {data}\n\n"
            last_signal = monotonic()
            if name in TERMINAL_EVENTS:
                return
        if events:
            continue
        remaining = keepalive - (monotonic() - last_signal)
        if remaining <= 0:
            yield ": keep-alive\n\n"
            last_signal = monotonic()
            remaining = keepalive
        await asyncio.sleep(min(remaining, poll_interval))
