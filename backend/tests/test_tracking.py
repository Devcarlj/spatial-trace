from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from core.tracking import build_track, estimate_camera, CameraEstimate
from core.verification import Detection


def _background(seed=5):
    rng = np.random.default_rng(seed)
    # Features spread across the frame, with unique local texture.
    image = np.full((480, 640, 3), 190, dtype=np.uint8)
    for _ in range(700):
        x, y = rng.integers([5, 5], [635, 475])
        cv2.circle(image, (int(x), int(y)), int(rng.integers(1, 5)), tuple(int(c) for c in rng.integers(0, 180, 3)), -1)
    return image


def _frame(tmp_path, name, image, ts):
    path = tmp_path / f"{name}.png"
    assert cv2.imwrite(str(path), image)
    return SimpleNamespace(id=name, timestamp=ts, frame_path=str(path))


def _hit(box, color=0, score=0.95):
    appearance = np.zeros(256, dtype=np.float32)
    appearance[color] = 1
    return Detection(score, list(box), appearance=appearance)


def _identity(*_args):
    return CameraEstimate(np.eye(2, 3), "Stable background")


def test_camera_pan_does_not_become_object_movement(isolated_env, tmp_path):
    image = _background()
    pan = np.float32([[1, 0, 28], [0, 1, 16]])
    old = _frame(tmp_path, "old", image, 1)
    new = _frame(tmp_path, "new", cv2.warpAffine(image, pan, (640, 480)), 2)
    old_hit, new_hit = _hit([120, 100, 200, 160]), _hit([148, 116, 228, 176])
    track, movement = build_track([(old, [old_hit]), (new, [new_hit])])
    assert len(track) == 2
    assert movement.status == "stationary"
    assert movement.camera_compensated
    assert np.linalg.norm(movement.displacement) < 2


def test_real_movement_survives_camera_compensation(isolated_env, tmp_path):
    image = _background()
    pan = np.float32([[1, 0, 28], [0, 1, 16]])
    old = _frame(tmp_path, "old", image, 1)
    new = _frame(tmp_path, "new", cv2.warpAffine(image, pan, (640, 480)), 2)
    _, movement = build_track([(old, [_hit([120, 100, 200, 160])]), (new, [_hit([248, 116, 328, 176])])])
    assert movement.status == "moved"
    assert movement.displacement[0] == pytest.approx(100, abs=2)


def test_zoom_and_rotation_are_compensated(isolated_env, tmp_path):
    image = _background()
    transform = cv2.getRotationMatrix2D((320, 240), 4, 1.08)
    old = _frame(tmp_path, "old", image, 1)
    new = _frame(tmp_path, "new", cv2.warpAffine(image, transform, (640, 480)), 2)
    center = transform[:, :2] @ np.array([160, 130]) + transform[:, 2]
    box = [center[0] - 43, center[1] - 32, center[0] + 43, center[1] + 32]
    _, movement = build_track([(old, [_hit([120, 100, 200, 160])]), (new, [_hit(box)])])
    assert movement.status == "stationary"


def test_scene_cut_suppresses_movement(isolated_env, tmp_path):
    old = _frame(tmp_path, "old", _background(1), 1)
    new = _frame(tmp_path, "new", _background(99), 2)
    _, movement = build_track([(old, [_hit([100, 100, 180, 160])]), (new, [_hit([400, 100, 480, 160])])])
    assert movement.status == "unknown"


def test_box_jitter_is_tolerated(isolated_env, monkeypatch):
    monkeypatch.setattr("core.tracking.estimate_camera", _identity)
    old, new = SimpleNamespace(timestamp=1), SimpleNamespace(timestamp=2)
    _, movement = build_track([(old, [_hit([100, 100, 180, 160])]), (new, [_hit([102, 101, 182, 161])])])
    assert movement.status == "stationary"


def test_appearance_prevents_high_score_identity_swap(isolated_env, monkeypatch):
    monkeypatch.setattr("core.tracking.estimate_camera", _identity)
    old, new = SimpleNamespace(timestamp=1), SimpleNamespace(timestamp=2)
    red, blue = _hit([100, 100, 180, 160], 1, .90), _hit([400, 100, 480, 160], 2, .99)
    track, movement = build_track([(old, [blue, red]), (new, [_hit([102, 101, 182, 161], 1)])])
    assert track[0][1] is red
    assert movement.status == "stationary"


def test_identical_instances_stop_association(isolated_env, monkeypatch):
    monkeypatch.setattr("core.tracking.estimate_camera", _identity)
    old, new = SimpleNamespace(timestamp=1), SimpleNamespace(timestamp=2)
    track, movement = build_track([(old, [_hit([100, 100, 180, 160]), _hit([120, 100, 200, 160])]),
                                   (new, [_hit([110, 100, 190, 160])])])
    assert len(track) == 1
    assert movement.status == "unknown"


def test_gap_and_occlusion_do_not_bridge_identity(isolated_env, monkeypatch):
    monkeypatch.setattr("core.tracking.estimate_camera", _identity)
    old, hidden, new = [SimpleNamespace(timestamp=t) for t in [1, 2, 45]]
    hit = _hit([100, 100, 180, 160])
    track, movement = build_track([(old, [hit]), (new, [hit])])
    assert len(track) == 1 and movement.status == "unknown"
    new.timestamp = 3
    track, movement = build_track([(old, [hit]), (hidden, []), (new, [hit])])
    assert len(track) == 1 and "occlusion" in movement.reason


def test_untextured_background_is_unknown(isolated_env, tmp_path):
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    old, new = _frame(tmp_path, "old", blank, 1), _frame(tmp_path, "new", blank, 2)
    estimate = estimate_camera(old, new, [], [])
    assert estimate.matrix is None


def test_accumulated_drift_and_move_then_return_are_detected(isolated_env, monkeypatch):
    monkeypatch.setattr("core.tracking.estimate_camera", _identity)
    frames = [SimpleNamespace(timestamp=t) for t in [1, 2, 3, 4]]
    # Each step is below tolerance but the total drift exceeds it.
    hits = [_hit([100 + x, 100, 180 + x, 160]) for x in [0, 7, 14, 21]]
    _, movement = build_track(list(zip(frames, [[hit] for hit in hits])))
    assert movement.status == "moved"
    hits = [_hit([100 + x, 100, 180 + x, 160]) for x in [0, 50, 0, 0]]
    _, movement = build_track(list(zip(frames, [[hit] for hit in hits])))
    assert movement.status == "moved"
    assert movement.displacement == [0, 0]
