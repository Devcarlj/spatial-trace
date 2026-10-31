from core.vlm_client import index_settled_frame
from main import QueryRequest, query_memory
import asyncio
import builtins

import pytest
from fastapi import HTTPException


def test_startup_rejects_missing_vision_dependency(isolated_env, monkeypatch):
    import main

    original_import = builtins.__import__

    def missing_cv2(name, *args, **kwargs):
        if name == "core.keyframer":
            raise ModuleNotFoundError("No module named 'cv2'", name="cv2")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_cv2)

    async def start():
        async with main.lifespan(main.app):
            pytest.fail("Backend accepted requests without its vision dependencies")

    with pytest.raises(RuntimeError, match="cv2.*run.ps1"):
        asyncio.run(start())


@pytest.mark.parametrize("module", ["core.keyframer", "core.query_service"])
def test_api_import_failure_returns_actionable_http_error(isolated_env, monkeypatch, module):
    import main

    original_import = builtins.__import__

    def missing_cv2(name, *args, **kwargs):
        if name == module:
            raise ModuleNotFoundError("No module named 'cv2'", name="cv2")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_cv2)
    with pytest.raises(HTTPException) as error:
        if module == "core.keyframer":
            main.index_video(main.IndexRequest(video_path="missing.mp4", clip_id="test"))
        else:
            main.query_memory(main.QueryRequest(query="keys"))
    assert error.value.status_code == 500
    assert "run.ps1" in error.value.detail


def _post_query(payload):
    """FastAPI runs the blocking pipeline in its synchronous worker pool."""
    return query_memory(QueryRequest(**payload))


def test_query_endpoint_returns_verified_result(isolated_env):
    index_settled_frame(
        "desk-01",
        1.0,
        "frames/frame-1.jpg",
        "desk_frame_01.jpg",
        [10, 20, 600, 400],
    )

    response = _post_query({"query": "keys"})

    assert response.state == "FOUND_NOW"
    assert response.bbox == [50.0, 220.0, 100.0, 260.0]
    assert response.frame_id


def test_query_endpoint_handles_empty_query(isolated_env):
    response = _post_query({"query": "  "})

    assert response.state == "UNSURE"
