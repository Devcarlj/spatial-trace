"""Keep all detections, with bounded full-frame / zoom / tile recovery."""

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path

import cv2
import numpy as np

from core.masks import decode_mask
from core.providers import get_model_client
from core.settings import get_settings
from core.files import atomic_write


@dataclass
class Detection:
    score: float
    bbox: list[float]
    mask: str | None = None
    recovered: bool = False
    appearance: np.ndarray | None = None


def overlap(a: list[float], b: list[float]) -> float:
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda box: (box[2] - box[0]) * (box[3] - box[1])
    return intersection / max(1, area(a) + area(b) - intersection)


def _appearance(image: np.ndarray | None, detection: Detection) -> np.ndarray | None:
    if image is None:
        return None
    x1, y1, x2, y2 = np.rint(detection.bbox).astype(int)
    height, width = image.shape[:2]
    roi = image[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]
    if roi.size == 0:
        return None
    mask = decode_mask(detection.mask)
    if mask is not None:
        mask = cv2.resize(mask, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST) * 255
        if not np.any(mask):
            return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], mask, [16, 4, 4], [0, 180, 0, 256, 0, 256])
    return cv2.normalize(hist, hist, norm_type=cv2.NORM_L1).flatten()


def _segment(path: str, noun: str, region: list[float], recovered: bool, input_size: tuple[int, int]) -> list[Detection]:
    response = get_model_client().sam_segment(path, noun)
    source_width, source_height = response.image_size or input_size
    x, y, width, height = region
    sx, sy = width / source_width, height / source_height
    detections = []
    for index, (box, score) in enumerate(zip(response.boxes, response.scores)):
        # Fixture providers use submitted-image coordinates when image_size is absent.
        if len(box) != 4 or not np.isfinite([*box, score]).all() or not 0 <= score <= 1:
            continue
        if not (0 <= box[0] < box[2] <= source_width and 0 <= box[1] < box[3] <= source_height):
            continue
        mapped = [x + box[0] * sx, y + box[1] * sy, x + box[2] * sx, y + box[3] * sy]
        mask = response.masks[index] if index < len(response.masks) else None
        detections.append(Detection(score, mapped, mask, recovered))
    return detections


def _recovery_image(image: np.ndarray, region: list[int]) -> tuple[str, tuple[int, int]]:
    x, y, width, height = region
    crop = image[y:y + height, x:x + width]
    # Increase small contexts without discarding the original full-resolution frame.
    scale = min(4.0, max(1.0, 512 / max(width, height)))
    if scale > 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    ok, encoded = cv2.imencode(".png", crop)
    if not ok:
        raise OSError("Could not prepare recovery image")
    digest = hashlib.sha256(encoded).hexdigest()
    folder = get_settings().data_dir / "recovery"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}.png"
    # Identical bytes + content-addressed names are safe across concurrent queries.
    if not path.is_file():
        atomic_write(path, encoded.tobytes())
    return str(path), (crop.shape[1], crop.shape[0])


def verify_frame(frame, noun: str) -> list[Detection]:
    # Attribute phrases for any base object ("person wearing a blue vest",
    # "dog with a red collar"): detect the base first, then confirm the
    # attribute on that instance's crop. Previously only person phrases
    # reached this two-stage check.
    clothing = re.fullmatch(r"(.+?) (?:wearing|in|with) (.+)", noun.strip().lower())
    if clothing:
        base = re.sub(r"^(?:a |an )", "", clothing.group(1)).strip()
        attribute = re.sub(r"^(?:a |an )", "", clothing.group(2)).strip()
        people = verify_frame(frame, base)
        image = cv2.imread(frame.frame_path)
        if image is None:
            return []
        height, width = image.shape[:2]
        accepted = []
        for hit in people:
            if hit.score < get_settings().sam_score_mid:
                continue
            x1, y1, x2, y2 = np.rint(hit.bbox).astype(int)
            left, top = max(0, x1), max(0, y1)
            right, bottom = min(width, x2), min(height, y2)
            if right <= left or bottom <= top:
                continue
            path, _ = _recovery_image(image, [left, top, right-left, bottom-top])
            if get_model_client().verify_attribute(path, attribute):
                accepted.append(hit)
        return accepted
    settings = get_settings()
    image = cv2.imread(frame.frame_path) if Path(frame.frame_path).is_file() else None
    x, y, width, height = frame.diff_bbox
    detections = _segment(frame.crop_path, noun, frame.diff_bbox, False, (int(width), int(height)))
    best = max(detections, key=lambda hit: hit.score, default=None)
    tiny = best is not None and min(best.bbox[2] - best.bbox[0], best.bbox[3] - best.bbox[1]) < settings.recovery_tiny_side
    if image is not None and settings.recovery_max_calls and (best is None or best.score < settings.sam_score_high or tiny):
        fh, fw = image.shape[:2]
        regions: list[list[int]] = []
        if best and best.score >= settings.sam_score_mid:
            bx1, by1, bx2, by2 = best.bbox
            padding = max(32, (bx2 - bx1), (by2 - by1))
            left, top = max(0, int(bx1 - padding)), max(0, int(by1 - padding))
            right, bottom = min(fw, int(bx2 + padding)), min(fh, int(by2 + padding))
            regions.append([left, top, right - left, bottom - top])
        full_region = [0, 0, fw, fh]
        if list(frame.diff_bbox) != full_region:
            regions.append(full_region)
        # Overlapping tiles expose objects missed in downsampled full frames.
        tw, th = max(1, round(fw * 0.6)), max(1, round(fh * 0.6))
        regions.extend([[left, top, tw, th] for top in (0, fh - th) for left in (0, fw - tw)])
        seen = {tuple(frame.diff_bbox)}
        calls = 0
        for region in regions:
            if calls >= settings.recovery_max_calls:
                break
            if tuple(region) in seen or min(region[2:]) <= 0:
                continue
            seen.add(tuple(region))
            path, size = _recovery_image(image, region)
            calls += 1
            recovered = _segment(path, noun, region, True, size)
            # A tiny confident seed should not be replaced by another instance elsewhere.
            if best and best.score >= settings.sam_score_high:
                recovered = [hit for hit in recovered if overlap(hit.bbox, best.bbox) >= 0.3]
            detections.extend(recovered)
            if any(hit.score >= settings.sam_score_high for hit in recovered):
                break
    # Merge repeated detections from overlapping recovery regions.
    unique: list[Detection] = []
    for hit in sorted(detections, key=lambda hit: hit.score, reverse=True):
        if not any(overlap(hit.bbox, other.bbox) > 0.5 for other in unique):
            hit.appearance = _appearance(image, hit)
            unique.append(hit)
    return unique
