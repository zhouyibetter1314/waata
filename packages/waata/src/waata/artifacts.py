"""Portable evidence types and the C5 storage interface."""

from datetime import timedelta
from typing import Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ArtifactKind = Literal["observation", "screenshot", "playwright_trace", "test_report"]
_MIME_TYPES = {
    "observation": "application/json",
    "screenshot": "image/png",
    "playwright_trace": "application/zip",
    "test_report": "application/json",
}


class _Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    case_id: str | None = None
    step_id: str | None = None
    tool_call_id: str | None = None
    kind: ArtifactKind
    mime_type: str
    captured_at: AwareDatetime

    @model_validator(mode="after")
    def validate_metadata(self) -> Self:
        if self.mime_type != _MIME_TYPES[self.kind]:
            raise ValueError("Evidence kind and media type must agree")
        if self.step_id is not None and self.case_id is None:
            raise ValueError("Step evidence requires a case ID")
        if self.captured_at.utcoffset() != timedelta(0):
            raise ValueError("Evidence timestamps must use UTC")
        return self


class ArtifactInput(_Artifact):
    content: bytes = Field(repr=False)


class ArtifactRef(_Artifact):
    artifact_id: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)


class ArtifactStore(Protocol):
    async def save(self, artifact: ArtifactInput) -> ArtifactRef:
        """Return only after the content and metadata are available to readers."""
