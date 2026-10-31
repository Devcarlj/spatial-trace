"""Pydantic contracts for pipeline I/O."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

QueryState = Literal["FOUND_NOW", "MOVED", "UNSURE"]


class VlmIndexOutput(BaseModel):
    objects: list[str]
    caption: str

    @field_validator("objects")
    @classmethod
    def _clean_labels(cls, value: list[str]) -> list[str]:
        # An empty list is a valid observation: dark, blank, or occluded frames
        # (e.g. an unlit bulb) may contain no identifiable object. Rejecting it
        # aborted indexing of a whole clip for one legitimately empty frame.
        return [item.strip() for item in value if item and item.strip()]

    @field_validator("caption")
    @classmethod
    def _caption_present(cls, value: str) -> str:
        caption = value.strip()
        if not caption:
            raise ValueError("caption must be non-empty")
        return caption


class SamResponse(BaseModel):
    boxes: list[list[float]] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    masks: list[str] = Field(default_factory=list)
    image_size: list[int] | None = None

    @field_validator("boxes")
    @classmethod
    def _box_shape(cls, value: list[list[float]]) -> list[list[float]]:
        for box in value:
            if len(box) != 4:
                raise ValueError("each SAM box must be [x1, y1, x2, y2]")
        return value


class MaskOverlay(BaseModel):
    """Decoded box-local PNG placed in half-open full-frame coordinates."""

    data_url: str
    bbox: list[float]
    width: int
    height: int


class MovementEvidence(BaseModel):
    status: Literal["moved", "stationary", "unknown"] = "unknown"
    reason: str
    displacement: list[float] | None = None
    camera_compensated: bool = False


class SpatialJson(BaseModel):
    surface: str
    anchor: str
    visibility: str


class TrailItem(BaseModel):
    frame_id: str
    frame_url: str | None = None
    ts: float | None = None
    bbox: list[float] | None = None
    score: float | None = None
    mask_overlay: MaskOverlay | None = None
    track_id: str | None = None
    recovered: bool = False


class QueryIntentModel(BaseModel):
    kind: Literal["locate", "last_seen", "first_seen", "moved"]
    target: str
    base_object: str
    attribute: str | None = None


class SearchReport(BaseModel):
    """What a query actually searched, so partial searches cannot look complete."""

    clip_id: str | None = None
    scope: str = ""
    frames_considered: int = 0
    frames_checked: int = 0
    frame_check_budget: int = 0
    budget_exhausted: bool = False
    complete: bool = True
    model_calls: int = 0
    cached_calls_reused: int = 0
    evidence_reused: int = 0
    refined: bool = False


class QueryResponse(BaseModel):
    clip_id: str | None = None
    last_seen_seconds: float | None = None
    state: QueryState
    bbox: list[float] | None = None
    mask: str | None = None
    trail: list[TrailItem] = Field(default_factory=list)
    answer: str
    query: str | None = None
    frame_path: str | None = None
    frame_id: str | None = None
    frame_url: str | None = None
    mask_overlay: MaskOverlay | None = None
    movement: MovementEvidence | None = None
    track_id: str | None = None
    score: float | None = None
    recovered: bool = False
    intent: QueryIntentModel | None = None
    search: SearchReport | None = None
    # [last verified sighting, next checked non-sighting] in clip seconds.
    # The true exit time lies inside; last_seen_seconds alone is sampled.
    last_seen_interval: list[float] | None = None
