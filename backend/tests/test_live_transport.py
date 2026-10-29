import json
import pytest
from core.live_transport import responses, parse_segmentation, ProviderUnavailable
from core.settings import Settings

def test_stream_contract_sends_image_and_requires_completion(monkeypatch, tmp_path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"image bytes")
    calls = []
    wire = "<0f>2<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10;c=0.91|><|mask;x=0;y=0;data=3,3,~abc|>"
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def iter_lines(self):
            for event in [{"type":"response.output_text.delta", "delta":wire}, {"type":"response.completed"}]:
                yield b"data: " + json.dumps(event).encode()
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()
    monkeypatch.setattr("core.live_transport.requests.post", post)
    text = responses(Settings(model_api_key="real-key"), "sam-3.1", "keys", str(image), True)
    assert calls[0][0].endswith("/responses")
    payload = calls[0][1]["json"]
    assert payload["metadata"]["include_confidence"] == "true"
    assert payload["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")
    assert parse_segmentation(text)["boxes"] == [[1,2,3,4]]
    assert parse_segmentation(text)["scores"] == [0.91]

def test_empty_segmentation_and_bad_confidence():
    assert parse_segmentation("") == {"boxes": [], "scores": [], "masks": []}
    with pytest.raises(ProviderUnavailable):
        parse_segmentation("<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10|><|mask;x=0;y=0;data=1,1,~a|>")

def test_cache_separates_mock_live_and_image_content(isolated_env, monkeypatch):
    from core.cache import cache_key
    from core.settings import reset_settings
    image = isolated_env / "frame.jpg"
    image.write_bytes(b"first")
    payload = {"image_path": str(image)}
    first = cache_key("sam", payload)
    image.write_bytes(b"second")
    assert first != cache_key("sam", payload)
    mock = cache_key("sam", payload)
    monkeypatch.setenv("SPATIALTRACE_MODE", "live")
    reset_settings()
    assert mock != cache_key("sam", payload)

def test_offline_snapshot_never_calls_provider(isolated_env, monkeypatch):
    from core.query_service import query_memory
    from core.settings import reset_settings
    expected = query_memory("keys")
    monkeypatch.setenv("OFFLINE_SNAPSHOTS", "1")
    reset_settings()
    monkeypatch.setattr("core.query_service.get_model_client", lambda: pytest.fail("offline must not call providers"))
    assert query_memory("keys") == expected
