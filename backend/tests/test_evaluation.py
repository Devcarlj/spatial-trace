from types import SimpleNamespace

import cv2
import numpy as np

from core.verification import Detection
from evaluate import evaluate_queries, evaluate_samples, grade
from evaluation_metrics import match_boxes, score_sample, summarize_samples


def test_duplicate_and_wrong_object_predictions_are_false_positives(tmp_path):
    sample = {"objects": [{"bbox": [0, 0, 10, 10]}]}
    predictions = [Detection(.9, [0, 0, 10, 10]), Detection(.9, [0, 0, 10, 10]), Detection(.9, [20, 20, 30, 30])]
    metrics = score_sample(sample, predictions, tmp_path)
    summary = summarize_samples([{"metrics": metrics}], 2)
    assert summary["true_positives"] == 1
    assert summary["false_positives"] == 2
    assert summary["detection_precision"] == 1 / 3
    assert summary["sampling_coverage"] == .5
    assert summary["mask_iou_mean"] is None


def test_matching_reassigns_to_avoid_losing_valid_pair():
    labels = [{"bbox": [0, 0, 10, 10]}, {"bbox": [4, 0, 14, 10]}]
    predictions = [Detection(.9, [2, 0, 12, 10]), Detection(.9, [0, 0, 8, 10])]
    assert len(match_boxes(labels, predictions)) == 2


def test_missed_detection_and_missing_mask_do_not_inflate_overlap(tmp_path, monkeypatch):
    cv2.imwrite(str(tmp_path / "mask.png"), np.ones((10, 10), dtype=np.uint8) * 255)
    sample = {"objects": [{"bbox": [0, 0, 10, 10], "mask_path": "mask.png"}]}
    assert score_sample(sample, [], tmp_path)["mask_ious"] == [0.0]
    hit = Detection(.9, [0, 0, 10, 10])
    assert score_sample(sample, [hit], tmp_path)["mask_ious"] == [0.0]
    monkeypatch.setattr("evaluation_metrics.decode_mask", lambda _: np.ones((2, 2), dtype=np.uint8))
    assert score_sample(sample, [hit], tmp_path)["mask_ious"] == [1.0]


def test_empty_negative_labels_and_no_samples_are_distinct(tmp_path):
    metrics = score_sample({"objects": []}, [Detection(.9, [0, 0, 10, 10])], tmp_path)
    assert metrics["false_positives"] == 1
    assert summarize_samples([], 0)["detection_recall"] is None


def test_stationary_case_catches_false_movement(monkeypatch):
    result = {"clip_id": "clip", "state": "MOVED", "last_seen_seconds": 8,
              "bbox": [0, 0, 10, 10], "movement": {"status": "moved"}}
    monkeypatch.setattr("evaluate.requests.post", lambda *a, **kw: SimpleNamespace(raise_for_status=lambda: None, json=lambda: result))
    case = {"query": "last time?", "expected_last_seen_seconds": 8, "expected_bbox": [0, 0, 10, 10], "expected_movement": "stationary"}
    report = evaluate_queries({"clip_id": "clip", "cases": [case]}, "http://local")
    assert report["passed"] == 0
    assert report["false_movement_rate"] == 1
    assert not grade(case, {**result, "clip_id": "other"}, "clip")[0]


def test_unindexed_labels_are_reported_as_missing(isolated_env, tmp_path):
    manifest = {"clip_id": "absent", "samples": [{"timestamp": 2, "target": "cup", "review_status": "reviewed", "objects": []}]}
    report = evaluate_samples(manifest, tmp_path)
    assert report["sampling_coverage"] == 0
    assert report["detection_precision"] is None
    assert "not indexed" in report["samples"][0]["error"]


def test_movement_cases_do_not_require_last_seen_labels(monkeypatch):
    case = {"kind": "movement", "query": "Did the cup move?", "expected_movement": "stationary"}
    result = {"clip_id": "clip", "state": "FOUND_NOW", "movement": {"status": "stationary"}}
    monkeypatch.setattr("evaluate.requests.post", lambda *a, **kw: SimpleNamespace(raise_for_status=lambda: None, json=lambda: result))
    report = evaluate_queries({"clip_id": "clip", "cases": [case]}, "http://local")
    assert report["passed"] == 1
    assert report["false_movement_rate"] == 0
    assert not grade(case, {**result, "state": "MOVED"}, "clip")[0]
