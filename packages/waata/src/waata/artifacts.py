"""C5 metadata and the caller-owned storage boundary (no storage implementation)."""

from typing import Literal, Protocol, Self

from pydantic import model_validator

from waata.core.models import ContractModel, NonBlank, NonNegativeInt, UTCTimestamp

ArtifactKind = Literal["observation", "screenshot", "playwright_trace", "test_report"]
MEDIA_TYPES = {
    "observation": "application/json",
    "screenshot": "image/png",
    "playwright_trace": "application/zip",
    "test_report": "application/json",
}


class ArtifactMetadata(ContractModel):
    run_id: NonBlank
    case_id: NonBlank | None
    step_id: NonBlank | None
    tool_call_id: NonBlank | None
    kind: ArtifactKind
    mime_type: NonBlank
    captured_at: UTCTimestamp

    @model_validator(mode="after")
    def check_metadata(self) -> Self:
        if self.step_id is not None and self.case_id is None:
            raise ValueError("step_id requires case_id")
        if self.mime_type != MEDIA_TYPES[self.kind]:
            raise ValueError("mime_type does not match artifact kind")
        return self


class ArtifactRef(ArtifactMetadata):
    artifact_id: NonBlank
    size_bytes: NonNegativeInt


class ArtifactInput(ArtifactMetadata):
    # The trusted caller must supply bounded, redacted bytes, per C5.
    content: bytes


class ArtifactStore(Protocol):
    async def save(self, artifact: ArtifactInput) -> ArtifactRef: ...
