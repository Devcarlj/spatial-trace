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


def test_process_video_persists_settled_change(isolated_env, tmp_path):
    clip = tmp_path / "motion.avi"
    _write_motion_clip(clip)

    indexed = process_video(clip, "desk-01")

    assert len(indexed) == 1
    result = indexed[0]
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
