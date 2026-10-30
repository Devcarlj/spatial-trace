"""Conservative association of sparse sightings, with background motion compensation.

These are query-local tracks, not SAM video IDs or proof of identity after occlusion.
"""

from dataclasses import dataclass
from pathlib import Path
import math

import cv2
import numpy as np

from core.contracts import MovementEvidence
from core.settings import get_settings
from core.verification import Detection


@dataclass
class CameraEstimate:
    matrix: np.ndarray | None
    reason: str


def estimate_camera(previous, current, previous_hits: list[Detection], current_hits: list[Detection]) -> CameraEstimate:
    """Fit background similarity motion; reject cuts, parallax and weak coverage."""
    images = []
    scales = []
    masks = []
    for frame, hits in ((previous, previous_hits), (current, current_hits)):
        image = cv2.imread(frame.frame_path, cv2.IMREAD_GRAYSCALE) if Path(frame.frame_path).is_file() else None
        if image is None:
            return CameraEstimate(None, "Frame pixels are unavailable for camera-motion checks.")
        scale = min(1, 960 / max(image.shape))
        image = cv2.resize(image, None, fx=scale, fy=scale)
        mask = np.full(image.shape, 255, dtype=np.uint8)
        for hit in hits:
            x1, y1, x2, y2 = np.rint(np.array(hit.bbox) * scale).astype(int)
            cv2.rectangle(mask, (x1 - 8, y1 - 8), (x2 + 8, y2 + 8), 0, -1)
        images.append(image)
        scales.append(scale)
        masks.append(mask)
    orb = cv2.ORB_create(nfeatures=1800)
    kp1, desc1 = orb.detectAndCompute(images[0], masks[0])
    kp2, desc2 = orb.detectAndCompute(images[1], masks[1])
    if desc1 is None or desc2 is None or min(len(desc1), len(desc2)) < 12:
        return CameraEstimate(None, "Too little background detail to separate object and camera motion.")
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(desc1, desc2, k=2)
    good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < 0.72 * pair[1].distance]
    if len(good) < 12:
        return CameraEstimate(None, "Backgrounds could not be aligned reliably; a scene cut or camera change is possible.")
    source = np.float32([kp1[item.queryIdx].pt for item in good]) / scales[0]
    target = np.float32([kp2[item.trainIdx].pt for item in good]) / scales[1]
    matrix, inliers = cv2.estimateAffinePartial2D(source, target, method=cv2.RANSAC,
                                               ransacReprojThreshold=3 / min(scales), maxIters=2000)
    if matrix is None or inliers is None:
        return CameraEstimate(None, "Background alignment failed.")
    accepted = inliers.ravel().astype(bool)
    if accepted.sum() < 12 or accepted.mean() < 0.55:
        return CameraEstimate(None, "Background motion is inconsistent, so movement is uncertain.")
    for points, image, scale in ((source[accepted], images[0], scales[0]), (target[accepted], images[1], scales[1])):
        span = np.ptp(points * scale, axis=0)
        if span[0] < image.shape[1] * 0.25 or span[1] < image.shape[0] * 0.25:
            return CameraEstimate(None, "Background matches cover too little of the frame.")
    zoom = math.hypot(matrix[0, 0], matrix[1, 0])
    residual = np.linalg.norm(source[accepted] @ matrix[:, :2].T + matrix[:, 2] - target[accepted], axis=1)
    if not 0.5 < zoom < 2 or np.median(residual) > 3 / min(scales):
        return CameraEstimate(None, "Camera alignment has too much residual error.")
    return CameraEstimate(matrix, "Background aligned with robust feature matches.")


def center(box: list[float]) -> np.ndarray:
    return np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])


def _match_cost(previous: Detection, current: Detection, camera: CameraEstimate) -> float | None:
    if previous.appearance is None or current.appearance is None:
        return None
    appearance = cv2.compareHist(previous.appearance, current.appearance, cv2.HISTCMP_BHATTACHARYYA)
    area = lambda hit: (hit.bbox[2] - hit.bbox[0]) * (hit.bbox[3] - hit.bbox[1])
    zoom_area = abs(np.linalg.det(camera.matrix[:, :2])) if camera.matrix is not None else 1
    ratio = area(current) / max(1, area(previous) * zoom_area)
    if appearance > 0.45 or not 0.4 <= ratio <= 2.5:
        return None
    # Appearance dominates. Geometry only breaks ties; a tie is treated as ambiguous.
    predicted = center(previous.bbox)
    if camera.matrix is not None:
        predicted = camera.matrix[:, :2] @ predicted + camera.matrix[:, 2]
    distance = np.linalg.norm(center(current.bbox) - predicted)
    diagonal = max(1, np.linalg.norm(np.array(previous.bbox[2:]) - previous.bbox[:2]))
    return float(appearance + 0.08 * min(3, distance / diagonal))


def build_track(observations: list[tuple[object, list[Detection]]]):
    """Anchor at the latest observation and stop at gaps or ambiguous associations."""
    settings = get_settings()
    observations = sorted(observations, key=lambda item: item[0].timestamp)
    latest_frame, latest_hits = observations[-1]
    latest_hit = max(latest_hits, key=lambda hit: hit.score)
    track = [(latest_frame, latest_hit)]
    comparisons = []
    reason = "Only one verified observation is available."
    current_frame, current_hit, current_hits = latest_frame, latest_hit, latest_hits
    for previous_frame, previous_hits in reversed(observations[:-1]):
        if not previous_hits:
            reason = "An intervening observation did not verify this object; identity across occlusion is uncertain."
            break
        gap = current_frame.timestamp - previous_frame.timestamp
        if not 0 < gap <= settings.tracking_max_gap_seconds:
            reason = "The observation gap is too large to associate identity safely."
            break
        camera = estimate_camera(previous_frame, current_frame, previous_hits, current_hits)
        costs = []
        # Mutual uniqueness: do not follow a lookalike when multiple instances compete.
        for hit in previous_hits:
            cost = _match_cost(hit, current_hit, camera)
            if cost is not None:
                costs.append((cost, hit))
        costs.sort(key=lambda item: item[0])
        if not costs or (len(costs) > 1 and costs[1][0] - costs[0][0] < 0.1):
            reason = "Object identity is ambiguous between observations."
            break
        previous_hit = costs[0][1]
        alternatives = sorted(cost for hit in current_hits if (cost := _match_cost(previous_hit, hit, camera)) is not None)
        if len(alternatives) > 1 and alternatives[1] - alternatives[0] < 0.1:
            reason = "Multiple similar objects prevent a reliable association."
            break
        track.insert(0, (previous_frame, previous_hit))
        comparisons.insert(0, (previous_hit, current_hit, camera))
        current_frame, current_hit, current_hits = previous_frame, previous_hit, previous_hits
    if not comparisons:
        return track, MovementEvidence(reason=reason)
    # Evaluate displacement from the oldest associated sighting, not just adjacent jitter.
    if any(camera.matrix is None for _, _, camera in comparisons):
        reason = next(camera.reason for _, _, camera in comparisons if camera.matrix is None)
        return track, MovementEvidence(reason=reason)
    origin = center(track[0][1].bbox)
    predicted = origin.copy()
    compensated = False
    for _, _, camera in comparisons:
        predicted = camera.matrix[:, :2] @ predicted + camera.matrix[:, 2]
        compensated |= not np.allclose(camera.matrix, np.eye(2, 3), atol=0.5)
    displacement = center(latest_hit.bbox) - predicted
    object_diagonal = np.linalg.norm(np.array(latest_hit.bbox[2:]) - latest_hit.bbox[:2])
    threshold = max(settings.movement_min_pixels, object_diagonal * settings.movement_relative_threshold)
    moved = np.linalg.norm(displacement) > threshold
    # A moved-then-returned object still moved, even when net displacement is zero.
    for previous_hit, current_hit, camera in comparisons:
        expected = camera.matrix[:, :2] @ center(previous_hit.bbox) + camera.matrix[:, 2]
        step = np.linalg.norm(center(current_hit.bbox) - expected)
        diagonal = np.linalg.norm(np.array(current_hit.bbox[2:]) - current_hit.bbox[:2])
        moved |= step > max(settings.movement_min_pixels, diagonal * settings.movement_relative_threshold)
    return track, MovementEvidence(
        status="moved" if moved else "stationary",
        reason="Movement between observations exceeds tolerance after background alignment." if moved else "Position changes stay within the movement tolerance after background alignment.",
        displacement=[round(float(value), 2) for value in displacement], camera_compensated=bool(compensated),
    )
