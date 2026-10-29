import pytest
from pydantic import ValidationError

from core.contracts import SamResponse, SpatialJson, VlmIndexOutput


def test_vlm_rejects_empty_objects():
    with pytest.raises(ValidationError):
        VlmIndexOutput(objects=[], caption="desk")


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
