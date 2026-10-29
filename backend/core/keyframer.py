"""Extract and index meaningful settled frames from a recorded clip."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.settings import get_settings


def compute_diff(prev_frame: np.ndarray, curr_frame: np.ndarray) -> tuple[float, np.ndarray]:
    """Return a motion score and image difference for equally sized gray frames."""
    diff = cv2.absdiff(prev_frame, curr_frame)
    return float(np.sum(diff)), diff


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
    if not clip_id or Path(clip_id).name != clip_id or clip_id in {".", ".."}:
        raise ValueError("clip_id must be a simple directory name")
    return clip_id


def process_video(video_path: str | Path, clip_id: str) -> list[dict[str, Any]]:
    """Index each post-motion settled region and return its persisted metadata."""
    from core.vlm_client import index_settled_frame

    settings = get_settings()
    source = Path(video_path)
    if not source.is_file():
        raise FileNotFoundError(f"Video does not exist: {source}")
    safe_clip_id = _safe_clip_id(clip_id)
    output_dir = settings.data_dir / "frames" / safe_clip_id
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise ValueError(f"Unable to read video: {source}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 3.0
    frame_skip = max(1, round(fps / 3))
    prev_gray_small: np.ndarray | None = None
    prev_full_frame: np.ndarray | None = None
    pre_motion_full_frame: np.ndarray | None = None
    motion_spike = False
    calm_frames = 0
    indexed: list[dict[str, Any]] = []
    frame_count = 0

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
            if prev_gray_small is not None and prev_full_frame is not None:
                diff_score, _ = compute_diff(prev_gray_small, gray_small)
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
                        x, y, width, height = bbox
                        crop = frame[y : y + height, x : x + width]
                        timestamp = frame_count / fps
                        frame_path = output_dir / f"frame_{frame_count}.jpg"
                        crop_path = output_dir / f"crop_{frame_count}.jpg"
                        if not cv2.imwrite(str(frame_path), frame) or not cv2.imwrite(str(crop_path), crop):
                            raise OSError("Could not write detected keyframe files")
                        frame_id = index_settled_frame(
                            safe_clip_id, timestamp, str(frame_path), str(crop_path), bbox
                        )
                        indexed.append(
                            {
                                "frame_id": frame_id,
                                "timestamp": timestamp,
                                "frame_path": str(frame_path),
                                "crop_path": str(crop_path),
                                "diff_bbox": bbox,
                            }
                        )
                    motion_spike = False
                    calm_frames = 0

            prev_gray_small = gray_small
            prev_full_frame = frame.copy()
            frame_count += 1
    finally:
        cap.release()
    # Moving-camera/short clips may never meet the settle window. Keep an
    # honest full-frame observation rather than returning a silent empty index.
    if not indexed and prev_full_frame is not None:
        height, width = prev_full_frame.shape[:2]
        frame_path = output_dir / "frame_fallback.jpg"
        if not cv2.imwrite(str(frame_path), prev_full_frame):
            raise OSError("Could not save fallback frame")
        timestamp = max(0, frame_count - 1) / fps
        bbox = [0, 0, width, height]
        frame_id = index_settled_frame(safe_clip_id, timestamp, str(frame_path), str(frame_path), bbox)
        indexed.append({"frame_id": frame_id, "timestamp": timestamp,
                        "frame_path": str(frame_path), "crop_path": str(frame_path), "diff_bbox": bbox})
    if prev_full_frame is None:
        raise ValueError("Video contains no decodable frames")
    return indexed
