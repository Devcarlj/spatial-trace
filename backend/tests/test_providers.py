import json

import pytest
import requests

from core.cache import cache_key, get_cached
from core.contracts import QueryResponse, SpatialJson, VlmIndexOutput
from core.providers import (
    LiveSamProvider,
    MockLlmProvider,
    MockSamProvider,
    MockVlmProvider,
    ModelClient,
    ProviderUnavailable,
    build_providers,
    get_model_client,
)
from core.settings import get_settings, reset_settings


def test_mock_sam_is_keyed_by_image_and_noun(isolated_env):
    sam = MockSamProvider()
    glasses = sam.segment("desk_frame_01.jpg", "reading glasses")
    keys = sam.segment("desk_frame_01.jpg", "keys")
    unknown = sam.segment("other.jpg", "widget")
    assert glasses["scores"][0] == pytest.approx(0.93)
    assert keys["boxes"] != glasses["boxes"]
    assert unknown["scores"][0] == pytest.approx(0.35)


def test_mock_llm_synonym_and_spatial(isolated_env):
    llm = MockLlmProvider()
    assert llm.normalize_query("where are my specs") == "reading glasses"
    spatial = SpatialJson.model_validate(llm.describe_spatial("crop.jpg", "reading glasses"))
    assert spatial.surface == "wooden desk"
    assert spatial.visibility == "fully visible"


def test_vlm_schema_retry_then_cache(isolated_env):
    client = get_model_client()
    assert isinstance(client.vlm, MockVlmProvider)

    result = client.vlm_describe("frames/bad_then_good.jpg")
    assert result == VlmIndexOutput(
        objects=["reading glasses"],
        caption="A pair of reading glasses after retry.",
    )
    assert client.vlm.attempts["bad_then_good.jpg"] == 2

    again = client.vlm_describe("frames/bad_then_good.jpg")
    assert again == result
    assert client.vlm.attempts["bad_then_good.jpg"] == 2
    assert get_cached(cache_key("cheap_vlm", {"crop_path": "frames/bad_then_good.jpg"})) is not None


def test_vlm_schema_retry_exhausted(isolated_env):
    client = get_model_client()
    with pytest.raises((json.JSONDecodeError, ValueError)):
        client.vlm_describe("always_bad.jpg")
    assert client.vlm.attempts["always_bad.jpg"] == 2


def test_sam_cached_call_does_not_reinvoke_provider(isolated_env):
    client = get_model_client()
    original = client.sam.segment

    calls = {"n": 0}

    def counting_segment(image_path, noun_phrase):
        calls["n"] += 1
        return original(image_path, noun_phrase)

    client.sam.segment = counting_segment
    first = client.sam_segment("desk_frame_01.jpg", "reading glasses")
    second = client.sam_segment("desk_frame_01.jpg", "reading glasses")
    assert first.scores[0] == pytest.approx(0.93)
    assert second.model_dump() == first.model_dump()
    assert calls["n"] == 1


def test_build_providers_follows_mode_flag(isolated_env, monkeypatch):
    monkeypatch.setenv("SPATIALTRACE_MODE", "live")
    monkeypatch.setenv("MODEL_API_KEY", "YOUR_HACKATHON_API_KEY")
    reset_settings()
    get_model_client.cache_clear()
    sam, vlm, llm = build_providers(get_settings())
    assert sam.__class__.__name__.startswith("Live")
    assert vlm.__class__.__name__.startswith("Live")
    assert llm.__class__.__name__.startswith("Live")


def test_live_sam_fails_closed_without_key(isolated_env):
    provider = LiveSamProvider(get_settings())
    with pytest.raises(ProviderUnavailable, match="MODEL_API_KEY"):
        provider.segment("frame.jpg", "keys")


def test_live_sam_fails_closed_on_401(isolated_env, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "real-looking-key")
    reset_settings()
    settings = get_settings()

    class FakeResponse:
        status_code = 401
        text = "unauthorized"
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass

    def fake_post(*_args, **_kwargs):
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    provider = LiveSamProvider(settings)
    image = isolated_env / "frame.jpg"
    image.write_bytes(b"image")
    with pytest.raises(ProviderUnavailable, match="401"):
        provider.segment(str(image), "keys")


def test_query_response_contract():
    payload = QueryResponse(
        state="FOUND_NOW",
        bbox=[120.0, 80.0, 260.0, 160.0],
        mask="mock://desk_frame_01/reading_glasses",
        trail=[],
        answer="The reading glasses are on the wooden desk.",
        query="where are my specs",
        frame_path="desk_frame_01.jpg",
        frame_id="frame-1",
    )
    assert payload.state == "FOUND_NOW"
    dumped = payload.model_dump()
    assert set(dumped) >= {"state", "bbox", "mask", "trail", "answer"}
