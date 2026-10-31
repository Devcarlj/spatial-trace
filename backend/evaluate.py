"""Evaluate labeled HTTP queries and optional indexed frame detections."""
import argparse
import hashlib
import json
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from core.query_service import _row_to_frame
from core.settings import get_settings
from core.verification import overlap, verify_frame
from database import get_db_path
from evaluation_metrics import average, score_sample, summarize_samples


def grade(case, result, clip_id):
    if result.get("clip_id") != clip_id:
        return False, None
    if case.get("kind") == "movement":
        expected_movement = case["expected_movement"]
        actual_movement = (result.get("movement") or {}).get("status")
        consistent = (result.get("state") == "MOVED") == (actual_movement == "moved")
        return actual_movement == expected_movement and consistent, None
    expected = case["expected_last_seen_seconds"]
    if expected is None:
        return (result.get("state") == "UNSURE" and result.get("last_seen_seconds") is None
                and result.get("bbox") is None), None
    actual = result.get("last_seen_seconds")
    iou = overlap(case["expected_bbox"], result["bbox"]) if result.get("bbox") else 0.0
    return (result.get("state") in {"FOUND_NOW", "MOVED"} and actual is not None
            and abs(actual - expected) <= case.get("tolerance_seconds", 0.5) and iou >= 0.5), iou


def evaluate_queries(manifest, url):
    outcomes = []
    for case in manifest.get("cases", []):
        start = time.perf_counter()
        outcome = {"query": case["query"], "passed": False}
        try:
            response = requests.post(url.rstrip("/") + "/api/query", json={"query": case["query"]}, timeout=600)
            response.raise_for_status()
            result = response.json()
            passed, iou = grade(case, result, manifest["clip_id"])
            expected_movement = case.get("expected_movement")
            actual_movement = (result.get("movement") or {}).get("status")
            claim = result.get("state") == "MOVED" or actual_movement == "moved"
            if expected_movement is not None:
                passed = passed and actual_movement == expected_movement
                if expected_movement != "moved" and claim:
                    passed = False
            expected, actual = case.get("expected_last_seen_seconds"), result.get("last_seen_seconds")
            outcome.update(passed=passed, box_iou=iou,
                           last_seen_error_seconds=abs(expected - actual)
                           if expected is not None and actual is not None and result.get("clip_id") == manifest["clip_id"] else None,
                           false_movement_claim=claim if expected_movement == "stationary" else None,
                           result={key: result.get(key) for key in ("state", "clip_id", "last_seen_seconds", "bbox", "score", "frame_id", "frame_url", "answer", "movement")})
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            outcome["error"] = str(exc)
        outcome["latency_seconds"] = round(time.perf_counter() - start, 3)
        outcomes.append(outcome)
    stationary = [item["false_movement_claim"] for item in outcomes if item.get("false_movement_claim") is not None]
    return {"passed": sum(item["passed"] for item in outcomes), "total": len(outcomes),
            "average_latency_seconds": average([item["latency_seconds"] for item in outcomes]),
            "mean_last_seen_error_seconds": average([item["last_seen_error_seconds"] for item in outcomes if item.get("last_seen_error_seconds") is not None]),
            "false_movement_rate": average(stationary), "stationary_case_count": len(stationary),
            "movement_labels_missing": sum("expected_movement" not in case for case in manifest.get("cases", [])),
            "uncertain_count": sum(item.get("result", {}).get("state") == "UNSURE" for item in outcomes),
            "error_count": sum("error" in item for item in outcomes), "cases": outcomes}


def evaluate_samples(manifest, manifest_dir):
    outcomes = []
    with sqlite3.connect(get_db_path().resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        for sample in manifest.get("samples", []):
            outcome = {"timestamp": sample["timestamp"], "target": sample["target"]}
            start = time.perf_counter()
            try:
                if sample.get("review_status") != "reviewed" or "objects" not in sample:
                    raise ValueError("Sample needs reviewed, exhaustive target labels (objects=[] for absent)")
                row = conn.execute("SELECT * FROM frames WHERE clip_id=? AND ABS(ts-?) < 0.001 ORDER BY rowid LIMIT 1",
                                   (manifest["clip_id"], sample["timestamp"])).fetchone()
                if row is None:
                    raise ValueError("Labeled timestamp is not indexed")
                frame = _row_to_frame(row)
                predictions = verify_frame(frame, sample["target"])
                outcome["metrics"] = score_sample(sample, predictions, manifest_dir)
                outcome["frame_id"] = frame.id
                outcome["predictions"] = [{"bbox": p.bbox, "score": p.score, "recovered": p.recovered} for p in predictions]
            except Exception as exc:
                outcome["error"] = str(exc)
            outcome["latency_seconds"] = round(time.perf_counter() - start, 3)
            outcomes.append(outcome)
    summary = summarize_samples(outcomes, len(manifest.get("samples", [])))
    summary["average_latency_seconds"] = average([item["latency_seconds"] for item in outcomes])
    return {**summary, "samples": outcomes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    parser.add_argument("--samples", action="store_true", help="Also verify indexed frames with local model settings")
    parser.add_argument("--cache-state", choices=("warm", "cold", "mixed", "unknown"), default="unknown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    if not manifest.get("cases") and not (args.samples and manifest.get("samples")):
        parser.error("Manifest has no requested evaluation cases")
    settings = get_settings()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=False).stdout
    # Allowlist prevents credentials from entering reports.
    configuration = {key: getattr(settings, key) for key in (
        "spatialtrace_mode", "offline_snapshots", "sam_model_name", "vlm_model_name", "llm_model_name",
        "sam_score_high", "sam_score_mid", "periodic_keyframe_interval_seconds", "scene_change_threshold",
        "scene_change_min_interval_seconds", "recovery_max_calls", "movement_min_pixels",
        "movement_relative_threshold", "tracking_max_gap_seconds")}
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "clip_id": manifest["clip_id"],
              "manifest_sha256": hashlib.sha256(raw).hexdigest(), "source": manifest.get("source"),
              "split": manifest.get("split", "unassigned"), "git_revision": revision, "working_tree_dirty": bool(dirty),
              "cache_state_declared": args.cache_state, "local_configuration": configuration,
              "http_configuration": "Not introspected; ensure server uses matching settings", "url": args.url,
              "queries": evaluate_queries(manifest, args.url)}
    if args.samples:
        report["detections"] = evaluate_samples(manifest, args.manifest.parent)
    else:
        report["detections"] = {"status": "not_run", "reason": "Use --samples for indexed frame verification"}
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    incomplete = args.samples and report["detections"]["evaluated_samples"] != report["detections"]["requested_samples"]
    detection_errors = args.samples and (report["detections"]["false_positives"] + report["detections"]["false_negatives"] > 0)
    return 0 if report["queries"]["passed"] == report["queries"]["total"] and not incomplete and not detection_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
