import pytest
from pydantic import ValidationError

from core.contracts import SamResponse, SpatialJson, VlmIndexOutput


def test_vlm_allows_empty_objects_for_dark_or_blank_frames():
    parsed = VlmIndexOutput(objects=[], caption="A nearly black frame.")
    assert parsed.objects == []


def test_vlm_still_rejects_empty_caption():
    with pytest.raises(ValidationError):
        VlmIndexOutput(objects=[], caption="  ")


def test_sam_rejects_malformed_box():
    with pytest.raises(ValidationError):
        SamResponse(boxes=[[1.0, 2.0]], scores=[0.9], masks=["x"])


def test_spatial_json_requires_three_fields():
    parsed = SpatialJson(surface="desk", anchor="left of the lamp", visibility="partial")
    assert parsed.model_dump() == {
        "surface": "desk",
        "anchor": "left of the lamp",
        "visibility": "partial",
    }
