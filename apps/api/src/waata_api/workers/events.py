"""Validate and redact C4 progress from the C2 callback."""

from collections.abc import Callable
from datetime import timedelta
from urllib.parse import urlsplit

from waata.core.events import TestEvent

_VERDICTS = {"passed", "failed", "blocked", "inconclusive"}
_FIELDS = {
    "plan.created": {"total_cases"},
    "case.started": {"name"},
    "agent.step.started": {"summary"},
    "tool.called": {"tool_call_id", "tool"},
    "tool.completed": {
        "tool_call_id",
        "tool",
        "success",
        "duration_ms",
        "error_code",
        "evidence_ids",
    },
    "case.verified": {"verdict"},
}


def _tool_detail(
    value: object, evidence: list[str], sanitize: Callable[[str], str]
) -> dict[str, str | bool]:
    if not isinstance(value, dict):
        return {}
    detail: dict[str, str | bool] = {}
    if value.get("phase") in ("start", "check", "result"):
        detail["phase"] = value["phase"]
    if value.get("condition") in (
        "url_equals",
        "url_path_starts_with",
        "title_equals",
        "exists",
        "visible",
        "count",
        "text_equals",
    ):
        detail["condition"] = value["condition"]
    if isinstance(target := value.get("target"), str) and target.strip():
        detail["target"] = sanitize(" ".join(target.split()))[:160]
    if isinstance(destination := value.get("destination"), str):
        try:
            url = urlsplit(destination)
            if (
                url.scheme in ("http", "https")
                and url.hostname
                and url.username is None
            ):
                detail["destination"] = sanitize(
                    url._replace(query="", fragment="").geturl()
                )[:512]
        except ValueError:
            pass
    if type(value.get("matched")) is bool:
        detail["matched"] = value["matched"]
    if value.get("screenshot_id") in evidence:
        detail["screenshot_id"] = value["screenshot_id"]
    return detail


def public_event(
    event: TestEvent,
    run_id: str,
    sanitize: Callable[[str], str],
) -> dict:
    payload = event.payload.copy()
    if (
        event.run_id != run_id
        or event.timestamp.utcoffset() != timedelta()
        or not _FIELDS[event.type] <= payload.keys()
    ):
        raise ValueError("Invalid WAATA progress event")

    # Publish only the contracted fields, even for a substitutable C2 engine.
    raw_detail = payload.get("detail")
    payload = {name: payload[name] for name in _FIELDS[event.type]}
    identifiers = [event.event_id, event.case_id, event.step_id]
    match event.type:
        case "plan.created":
            total = payload["total_cases"]
            if type(total) is not int or total < 0:
                raise ValueError("Invalid plan progress")
        case "case.started":
            if not isinstance(payload["name"], str):
                raise ValueError("Invalid case progress")
            payload["name"] = sanitize(payload["name"])
        case "agent.step.started":
            summary = payload["summary"]
            if summary is not None:
                if not isinstance(summary, str):
                    raise ValueError("Invalid step summary")
                payload["summary"] = sanitize(summary)
        case "tool.called" | "tool.completed":
            if not payload["tool_call_id"] or not payload["tool"]:
                raise ValueError("Invalid tool identifiers")
            identifiers.extend([payload["tool_call_id"], payload["tool"]])
            if event.type == "tool.completed":
                success, duration = payload["success"], payload["duration_ms"]
                error, evidence = payload["error_code"], payload["evidence_ids"]
                if (
                    type(success) is not bool
                    or type(duration) is not int
                    or duration < 0
                    or success != (error is None)
                    or not isinstance(evidence, list)
                    or not all(isinstance(item, str) and item for item in evidence)
                ):
                    raise ValueError("Invalid tool progress")
                identifiers.extend([error, *evidence])
                if detail := _tool_detail(raw_detail, evidence, sanitize):
                    payload["detail"] = detail
        case "case.verified":
            if payload["verdict"] not in _VERDICTS:
                raise ValueError("Invalid case verdict")

    for value in identifiers:
        if value is not None and (
            not isinstance(value, str) or not value or sanitize(value) != value
        ):
            raise ValueError("Invalid progress identifier")

    return {**event.model_dump(mode="json", exclude={"payload"}), "payload": payload}
