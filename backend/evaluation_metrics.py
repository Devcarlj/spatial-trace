"""Metrics for explicitly labeled frame samples; unlabeled data is never a negative."""
from pathlib import Path

import cv2
import numpy as np

from core.masks import decode_mask
from core.verification import overlap


def match_boxes(expected, predictions, threshold=0.5):
    """Maximum one-to-one matching at the IoU threshold (duplicates are false positives)."""
    assigned = {}

    def assign(label, seen):
        candidates = sorted(range(len(predictions)),
                            key=lambda p: overlap(expected[label]["bbox"], predictions[p].bbox), reverse=True)
        for prediction in candidates:
            if prediction in seen or overlap(expected[label]["bbox"], predictions[prediction].bbox) < threshold:
                continue
            seen.add(prediction)
            if prediction not in assigned or assign(assigned[prediction], seen):
                assigned[prediction] = label
                return True
        return False

    for label in range(len(expected)):
        assign(label, set())
    return sorted((label, prediction) for prediction, label in assigned.items())


def mask_iou(label, detection, manifest_dir):
    """Compare a full-frame binary PNG label with SAM's box-local raster."""
    expected = cv2.imread(str(Path(manifest_dir) / label["mask_path"]), cv2.IMREAD_GRAYSCALE)
    if expected is None or not np.any(expected):
        raise ValueError("Mask label must be a readable, nonempty full-frame PNG")
    if detection is None:
        return 0.0
    raster = decode_mask(detection.mask)
    if raster is None:
        return 0.0
    x1, y1, x2, y2 = [round(v) for v in detection.bbox]
    height, width = expected.shape
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("Predicted mask box lies outside label image")
    actual = np.zeros_like(expected, dtype=bool)
    actual[y1:y2, x1:x2] = cv2.resize(raster, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST) > 0
    expected = expected > 0
    return float(np.count_nonzero(actual & expected) / np.count_nonzero(actual | expected))


def score_sample(sample, predictions, manifest_dir):
    labels = sample["objects"]
    for label in labels:
        box = label["bbox"]
        if len(box) != 4 or box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("Labels require positive-area xyxy boxes")
    matches = match_boxes(labels, predictions)
    matched = dict(matches)
    return {
        "true_positives": len(matches), "false_positives": len(predictions) - len(matches),
        "false_negatives": len(labels) - len(matches),
        "box_ious": [overlap(labels[g]["bbox"], predictions[p].bbox) for g, p in matches],
        "mask_ious": [mask_iou(label, predictions[matched[g]] if g in matched else None, manifest_dir)
                      for g, label in enumerate(labels) if label.get("mask_path")],
        "mask_labels_missing": sum(not label.get("mask_path") for label in labels),
    }


def average(values):
    return sum(values) / len(values) if values else None


def summarize_samples(outcomes, requested):
    measured = [item for item in outcomes if "metrics" in item]
    tp = sum(item["metrics"]["true_positives"] for item in measured)
    fp = sum(item["metrics"]["false_positives"] for item in measured)
    fn = sum(item["metrics"]["false_negatives"] for item in measured)
    boxes = [v for item in measured for v in item["metrics"]["box_ious"]]
    masks = [v for item in measured for v in item["metrics"]["mask_ious"]]
    return {"requested_samples": requested, "evaluated_samples": len(measured),
            "sampling_coverage": len(measured) / requested if requested else None,
            "true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "detection_precision": tp / (tp + fp) if tp + fp else None,
            "detection_recall": tp / (tp + fn) if tp + fn else None,
            "matched_box_iou_mean": average(boxes), "mask_iou_mean": average(masks),
            "mask_label_count": len(masks),
            "mask_labels_missing": sum(item["metrics"]["mask_labels_missing"] for item in measured)}
