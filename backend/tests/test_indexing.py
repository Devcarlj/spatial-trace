import sqlite3

import cv2
import numpy as np

from core.keyframer import process_video
from core.settings import get_settings


def _write_motion_clip(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 3, (96, 64))
    assert writer.isOpened()
    black = np.zeros((64, 96, 3), dtype=np.uint8)
    white = np.full((64, 96, 3), 255, dtype=np.uint8)
    writer.write(black)
    for _ in range(8):
        writer.write(white)
    writer.release()


def _write_static_clip(path, frame_count=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 3, (96, 64))
    assert writer.isOpened()
    frame = np.full((64, 96, 3), 127, dtype=np.uint8)
    for _ in range(frame_count):
        writer.write(frame)
    writer.release()


def _write_alternating_clip(path, frame_count=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 3, (96, 64))
    assert writer.isOpened()
    black = np.zeros((64, 96, 3), dtype=np.uint8)
    white = np.full((64, 96, 3), 255, dtype=np.uint8)
    for index in range(frame_count):
        writer.write(black if index % 2 else white)
    writer.release()


def test_process_video_adds_periodic_full_frame_observations(isolated_env, tmp_path):
    clip = tmp_path / "static.avi"
    _write_static_clip(clip)

    indexed = process_video(clip, "periodic-01")

    assert [item["timestamp"] for item in indexed] == [0.0, 2.0]
    assert [item["sampling_reason"] for item in indexed] == ["periodic", "periodic"]
    assert all(item["diff_bbox"] == [0, 0, 96, 64] for item in indexed)


def test_process_video_does_not_duplicate_periodic_scene_change_timestamps(isolated_env, tmp_path):
    clip = tmp_path / "alternating.avi"
    _write_alternating_clip(clip)
    settings = get_settings()
    settings.scene_change_threshold = 1
    settings.scene_change_min_interval_seconds = 0.1

    indexed = process_video(clip, "unique-timestamps")

    timestamps = [item["timestamp"] for item in indexed]
    assert len(timestamps) == len(set(timestamps))


def test_process_video_persists_settled_change(isolated_env, tmp_path):
    clip = tmp_path / "motion.avi"
    _write_motion_clip(clip)

    indexed = process_video(clip, "desk-01")

    result = next(item for item in indexed if item["sampling_reason"] == "settled_change")
    assert result["timestamp"] == 7.0 / 3.0
    assert result["diff_bbox"]
    assert result["frame_path"].endswith("frame_7.jpg")
    assert result["crop_path"].endswith("crop_7.jpg")

    conn = sqlite3.connect(get_settings().db_path)
    try:
        row = conn.execute(
            "SELECT clip_id, caption, objects_json FROM frames WHERE id = ?", (result["frame_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "desk-01"
    assert row[1]
    assert "keys" in row[2]


def test_process_video_rejects_unsafe_clip_id(isolated_env, tmp_path):
    clip = tmp_path / "motion.avi"
    _write_motion_clip(clip)

    try:
        process_video(clip, "../outside")
    except ValueError as exc:
        assert "clip_id" in str(exc)
    else:
        raise AssertionError("unsafe clip_id should be rejected")


def test_reindex_cannot_overwrite_existing_evidence(isolated_env, tmp_path):
    import pytest
    clip = tmp_path / "motion.avi"
    _write_motion_clip(clip)
    result = process_video(clip, "keep-evidence")[0]
    from pathlib import Path
    original = Path(result["frame_path"]).read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        process_video(clip, "keep-evidence")
    assert Path(result["frame_path"]).read_bytes() == original
