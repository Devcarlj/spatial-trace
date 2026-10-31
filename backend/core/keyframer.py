"""Extract and index meaningful settled frames from a recorded clip."""

from __future__ import annotations

from pathlib import Path
import json
import re
import sqlite3
from typing import Any

import cv2
import numpy as np

from core.settings import get_settings
from database import get_db_path, init_db, upsert_clip


def compute_diff(prev_frame: np.ndarray, curr_frame: np.ndarray) -> tuple[float, np.ndarray]:
    """Return a motion score and image difference for equally sized gray frames."""
    diff = cv2.absdiff(prev_frame, curr_frame)
    return float(np.sum(diff)), diff


def is_camera_pan(prev_gray: np.ndarray, curr_gray: np.ndarray) -> bool:
    """True when the dominant change is one global translation (a pan).

    A pan makes every pixel differ, which previously flooded the index with
    redundant scene-change samples. Phase correlation separates that global
    shift from a local object change; periodic samples still cover pans.
    """
    settings = get_settings()
    if settings.scene_pan_min_shift_pixels <= 0:
        return False
    try:
        (dx, dy), response = cv2.phaseCorrelate(
            np.float32(prev_gray), np.float32(curr_gray))
    except cv2.error:
        return False
    shift = float(np.hypot(dx, dy))
    return shift >= settings.scene_pan_min_shift_pixels and response >= settings.scene_pan_min_response


def get_region_diff_bbox(
    pre_motion_frame: np.ndarray,
    post_settle_frame: np.ndarray,
    min_diff_area: int,
) -> list[int] | None:
    """Return ``[x, y, width, height]`` for the largest meaningful change."""
    gray1 = cv2.cvtColor(pre_motion_frame, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(post_settle_frame, cv2.COLOR_BGR2GRAY)
    gray1 = cv2.GaussianBlur(gray1, (21, 21), 0)
    gray2 = cv2.GaussianBlur(gray2, (21, 21), 0)
    diff = cv2.absdiff(gray1, gray2)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    thresh = cv2.dilate(thresh, None, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < min_diff_area:
        return None
    x, y, width, height = cv2.boundingRect(largest)
    return [int(x), int(y), int(width), int(height)]


def _safe_clip_id(clip_id: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", clip_id) is None:
        raise ValueError("clip_id must contain 1-64 letters, digits, underscores or hyphens")
    return clip_id


def _existing_frames(clip_id: str) -> dict[float, dict[str, Any]]:
    init_db(get_db_path())
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM frames WHERE clip_id=?", (clip_id,)).fetchall()
    finally:
        conn.close()
    return {row["ts"]: {"frame_id": row["id"], "timestamp": row["ts"],
                        "frame_path": row["frame_path"], "crop_path": row["crop_path"],
                        "diff_bbox": json.loads(row["diff_bbox"]),
                        "sampling_reason": row["sampling_reason"] if "sampling_reason" in row.keys() else None}
            for row in rows}


def process_video(video_path: str | Path, clip_id: str) -> list[dict[str, Any]]:
    """Index periodic, scene-change, and post-motion observations from a clip.

    Clip lifecycle is explicit in the ``clips`` table: indexing -> ready when
    every sampled frame indexed, partial when some frames failed but usable
    evidence exists, failed when nothing could be indexed. Only ready clips
    are protected from re-indexing; partial/failed clips may be retried
    safely - timestamps already in the database are reused, not duplicated.
    """
    from core.vlm_client import index_settled_frame

    settings = get_settings()
    source = Path(video_path)
    if not source.is_file():
        raise FileNotFoundError(f"Video does not exist: {source}")
    safe_clip_id = _safe_clip_id(clip_id)
    output_dir = settings.data_dir / "frames" / safe_clip_id

    existing = _existing_frames(safe_clip_id)
    from database import get_clip
    clip_row = get_clip(safe_clip_id)
    if clip_row and clip_row["status"] == "ready" and existing:
        raise ValueError("This clip name already exists. Use a new clip name to preserve earlier evidence.")
    retrying = bool(existing)

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        upsert_clip(safe_clip_id, source_path=str(source), status="failed",
                    error="Unable to read video")
        raise ValueError(f"Unable to read video: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    upsert_clip(safe_clip_id, source_path=str(source), status="indexing", error=None)

    fps = cap.get(cv2.CAP_PROP_FPS) or 3.0
    frame_skip = max(1, round(fps / 3))
    prev_gray_small: np.ndarray | None = None
    prev_full_frame: np.ndarray | None = None
    pre_motion_full_frame: np.ndarray | None = None
    motion_spike = False
    calm_frames = 0
    indexed: list[dict[str, Any]] = []
    indexed_timestamps: set[float] = set()
    failed_frames = 0
    frame_count = 0
    next_periodic_timestamp = 0.0
    last_scene_change_timestamp: float | None = None

    def persist(frame: np.ndarray, timestamp: float, bbox: list[int], reason: str) -> None:
        nonlocal failed_frames
        # One observation per timestamp, whichever sampler fired first; on a
        # retry, timestamps already indexed are reused without a model call.
        if timestamp in indexed_timestamps:
            return
        indexed_timestamps.add(timestamp)
        if timestamp in existing:
            indexed.append(existing[timestamp])
            return
        x, y, width, height = bbox
        frame_path = output_dir / f"frame_{frame_count}.jpg"
        crop_path = output_dir / f"crop_{frame_count}.jpg"
        crop = frame[y : y + height, x : x + width]
        if not cv2.imwrite(str(frame_path), frame) or not cv2.imwrite(str(crop_path), crop):
            failed_frames += 1
            return
        try:
            frame_id = index_settled_frame(safe_clip_id, timestamp, str(frame_path), str(crop_path), bbox, reason)
        except Exception:
            # One bad frame (provider/schema failure) must not abort the clip:
            # it becomes partial evidence with an explicit failed count.
            failed_frames += 1
            return
        indexed.append(
            {
                "frame_id": frame_id,
                "timestamp": timestamp,
                "frame_path": str(frame_path),
                "crop_path": str(crop_path),
                "diff_bbox": bbox,
                "sampling_reason": reason,
            }
        )

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % frame_skip != 0:
                frame_count += 1
                continue

            small = cv2.resize(frame, (640, 360))
            gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            timestamp = frame_count / fps
            height, width = frame.shape[:2]
            full_frame_bbox = [0, 0, width, height]

            if timestamp >= next_periodic_timestamp:
                persist(frame, timestamp, full_frame_bbox, "periodic")
                while next_periodic_timestamp <= timestamp:
                    next_periodic_timestamp += settings.periodic_keyframe_interval_seconds

            if prev_gray_small is not None and prev_full_frame is not None:
                diff_score, _ = compute_diff(prev_gray_small, gray_small)
                pan = is_camera_pan(prev_gray_small, gray_small)
                if not pan:
                    if (diff_score >= settings.scene_change_threshold
                            and (last_scene_change_timestamp is None
                                 or timestamp - last_scene_change_timestamp >= settings.scene_change_min_interval_seconds)):
                        persist(frame, timestamp, full_frame_bbox, "scene_change")
                        last_scene_change_timestamp = timestamp
                    if diff_score > settings.settle_spike_threshold:
                        if not motion_spike:
                            pre_motion_full_frame = prev_full_frame
                        motion_spike = True
                        calm_frames = 0
                    elif motion_spike and diff_score < settings.settle_calm_threshold:
                        calm_frames += 1

                    if motion_spike and calm_frames >= settings.settle_calm_frames:
                        bbox = (
                            get_region_diff_bbox(pre_motion_full_frame, frame, settings.min_diff_area)
                            if pre_motion_full_frame is not None
                            else None
                        )
                        if bbox:
                            persist(frame, timestamp, bbox, "settled_change")
                        motion_spike = False
                        calm_frames = 0
                # During a pan the background itself is moving: do not treat
                # it as object motion or a scene change. Periodic samples
                # above still provide coverage.

            prev_gray_small = gray_small
            prev_full_frame = frame.copy()
            frame_count += 1
    except Exception:
        status = "partial" if indexed else "failed"
        upsert_clip(safe_clip_id, status=status, frame_count=len(indexed),
                    failed_frame_count=failed_frames, error="Indexing interrupted; retry is safe")
        raise
    finally:
        cap.release()
    # Moving-camera/short clips may never meet the settle window. Keep an
    # honest full-frame observation rather than returning a silent empty index.
    if not indexed and prev_full_frame is not None:
        height, width = prev_full_frame.shape[:2]
        frame_path = output_dir / "frame_fallback.jpg"
        if cv2.imwrite(str(frame_path), prev_full_frame):
            timestamp = max(0, frame_count - 1) / fps
            bbox = [0, 0, width, height]
            try:
                frame_id = index_settled_frame(safe_clip_id, timestamp, str(frame_path), str(frame_path), bbox, "fallback")
                indexed.append({"frame_id": frame_id, "timestamp": timestamp,
                                "frame_path": str(frame_path), "crop_path": str(frame_path), "diff_bbox": bbox,
                                "sampling_reason": "fallback"})
            except Exception:
                failed_frames += 1
    if prev_full_frame is None:
        upsert_clip(safe_clip_id, status="failed", frame_count=0,
                    failed_frame_count=failed_frames, error="Video contains no decodable frames")
        raise ValueError("Video contains no decodable frames")
    status = "ready" if failed_frames == 0 and indexed else ("partial" if indexed else "failed")
    upsert_clip(safe_clip_id, status=status, frame_count=len(indexed),
                failed_frame_count=failed_frames,
                error=None if status == "ready" else f"{failed_frames} sampled frame(s) failed to index")
    return indexed
