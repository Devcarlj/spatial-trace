from types import SimpleNamespace

import cv2
import numpy as np

from core.contracts import SamResponse
from core.verification import verify_frame
from core.settings import get_settings


def _frame(tmp_path):
    image = np.zeros((800, 1200, 3), dtype=np.uint8)
    full, crop = tmp_path / "full.png", tmp_path / "crop.png"
    assert cv2.imwrite(str(full), image)
    assert cv2.imwrite(str(crop), image[200:600, 100:700])
    return SimpleNamespace(frame_path=str(full), crop_path=str(crop), diff_bbox=[100, 200, 600, 400])


def test_provider_geometry_rescaled_to_full_frame(isolated_env, tmp_path, monkeypatch):
    frame = _frame(tmp_path)
    get_settings().recovery_max_calls = 0
    client = SimpleNamespace(sam_segment=lambda *_: SamResponse(boxes=[[20, 30, 100, 80]], scores=[.95], image_size=[300, 200]))
    monkeypatch.setattr("core.verification.get_model_client", lambda: client)
    hits = verify_frame(frame, "keys")
    assert hits[0].bbox == [140, 260, 300, 360]


def test_weak_seed_zoom_recovers_and_maps_original_coordinates(isolated_env, tmp_path, monkeypatch):
    frame = _frame(tmp_path)
    calls = []
    def segment(path, noun):
        calls.append(path)
        if len(calls) == 1:
            return SamResponse(boxes=[[40, 40, 50, 50]], scores=[.6])
        # Zoom context: [108,208,74,74], resized to 296x296 (4x).
        image = cv2.imread(path)
        assert image.shape[:2] == (296, 296)
        return SamResponse(boxes=[[128, 128, 168, 168]], scores=[.96], image_size=[296, 296])
    monkeypatch.setattr("core.verification.get_model_client", lambda: SimpleNamespace(sam_segment=segment))
    hits = verify_frame(frame, "keys")
    assert len(calls) == 2
    assert hits[0].recovered
    assert hits[0].bbox == [140, 240, 150, 250]


def test_full_frame_fallback_finds_object_outside_motion_crop(isolated_env, tmp_path, monkeypatch):
    frame = _frame(tmp_path)
    calls = []
    def segment(path, noun):
        calls.append(path)
        return SamResponse() if len(calls) == 1 else SamResponse(boxes=[[950, 100, 1050, 180]], scores=[.9], image_size=[1200, 800])
    monkeypatch.setattr("core.verification.get_model_client", lambda: SimpleNamespace(sam_segment=segment))
    hits = verify_frame(frame, "keys")
    assert hits[0].bbox == [950, 100, 1050, 180]
    assert hits[0].recovered and len(calls) == 2


def test_recovery_call_budget_and_invalid_geometry(isolated_env, tmp_path, monkeypatch):
    frame = _frame(tmp_path)
    get_settings().recovery_max_calls = 2
    calls = []
    def segment(path, noun):
        calls.append(path)
        return SamResponse(boxes=[[-10, 0, 20, 20]], scores=[.99])
    monkeypatch.setattr("core.verification.get_model_client", lambda: SimpleNamespace(sam_segment=segment))
    assert verify_frame(frame, "keys") == []
    assert len(calls) == 3  # initial + two extra, never an unbounded tile sweep
