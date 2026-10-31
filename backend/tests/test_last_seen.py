from types import SimpleNamespace

from core.contracts import QueryResponse
from core.query_service import query_memory
from core.verification import Detection, verify_frame
from evaluate import grade
from test_query_service import _insert_frame


def test_last_seen_checks_older_uncaptioned_frames(isolated_env, monkeypatch):
    for index in range(15):
        _insert_frame(str(index), float(index), "unknown.jpg", ["water"])
    monkeypatch.setattr("core.query_service.get_model_client", lambda: SimpleNamespace(normalize_query=lambda _: "person wearing blue vest"))
    monkeypatch.setattr("core.query_service.verify_frame", lambda frame, _: [Detection(.95, [1, 2, 30, 40])] if frame.timestamp == 2 else [])
    result = query_memory("When was the person last seen?")
    assert result.last_seen_seconds == 2
    assert result.clip_id == "desk-01"
    assert "sampled" in result.answer


def test_attribute_rejects_wrong_clothes(isolated_env, tmp_path, monkeypatch):
    import cv2
    import numpy as np
    from core.contracts import SamResponse
    from core.settings import get_settings
    path = tmp_path / "person.png"
    cv2.imwrite(str(path), np.zeros((100, 100, 3), dtype=np.uint8))
    get_settings().recovery_max_calls = 0
    prompts = []
    def segment(_, noun):
        prompts.append(noun)
        return SamResponse(boxes=[[10, 10, 90, 90]], scores=[.95])
    monkeypatch.setattr("core.verification.get_model_client", lambda: SimpleNamespace(sam_segment=segment, verify_attribute=lambda *_: False))
    frame = SimpleNamespace(frame_path=str(path), crop_path=str(path), diff_bbox=[0, 0, 100, 100])
    assert verify_frame(frame, "person wearing a blue shirt") == []
    assert prompts == ["person"]


def test_evaluator_rejects_wrong_clip_and_timestamp():
    case = {"expected_last_seen_seconds": 8, "expected_bbox": [0, 0, 10, 10]}
    result = QueryResponse(state="FOUND_NOW", answer="", clip_id="clip", last_seen_seconds=8, bbox=[0, 0, 10, 10]).model_dump()
    assert grade(case, result, "clip")[0]
    assert not grade(case, result, "other")[0]
    result["last_seen_seconds"] = 12
    assert not grade(case, result, "clip")[0]
