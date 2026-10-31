"""Milestone 2: clip selection, structured intent, budgets, refinement,
pan-aware sampling, and partial/failed indexing with safe retry."""

import json
import sqlite3
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from core.intent import parse_intent, split_attribute
from core.keyframer import process_video
from core.query_service import query_memory
from core.settings import get_settings
from core.verification import Detection
from database import get_clip, init_db, upsert_clip


def _insert(frame_id, ts, crop, objects, clip="desk-01"):
    db = get_settings().db_path
    init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO frames (id, clip_id, ts, frame_path, crop_path, diff_bbox, caption, objects_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (frame_id, clip, ts, f"frames/{frame_id}.jpg", crop,
             json.dumps([10, 20, 600, 400]), f"A scene containing {', '.join(objects)}.", json.dumps(objects)))
        conn.commit()
    finally:
        conn.close()


# -- structured intent -------------------------------------------------------

def test_intent_parses_temporal_kinds_and_targets():
    last = parse_intent("What is the last time there is a person wearing a blue vest?",
                        "person wearing a blue vest")
    assert last.kind == "last_seen"
    assert last.base_object == "person"
    assert last.attribute == "blue vest"

    first = parse_intent("When did the mug first appear?", "mug")
    assert first.kind == "first_seen"
    assert first.target == "mug"

    moved = parse_intent("Did the laptop move?", "laptop")
    assert moved.kind == "moved"
    assert moved.target == "laptop"

    locate = parse_intent("Where are my glasses?", "reading glasses")
    assert locate.kind == "locate"
    assert locate.target == "reading glasses"  # synonym expansion survives


def test_attribute_split_generalizes_beyond_person():
    assert split_attribute("dog with a red collar") == ("dog", "red collar")
    assert split_attribute("person in a blue jacket") == ("person", "blue jacket")
    assert split_attribute("red mug") == ("mug", "red")
    assert split_attribute("reading glasses") == ("reading glasses", None)


def test_attribute_verification_applies_to_any_base(isolated_env, tmp_path, monkeypatch):
    from core.contracts import SamResponse
    from core.verification import verify_frame
    path = tmp_path / "pet.png"
    cv2.imwrite(str(path), np.zeros((100, 100, 3), dtype=np.uint8))
    get_settings().recovery_max_calls = 0
    prompts = []
    def segment(_, noun):
        prompts.append(noun)
        return SamResponse(boxes=[[10, 10, 90, 90]], scores=[.95])
    monkeypatch.setattr("core.verification.get_model_client",
                        lambda: SimpleNamespace(sam_segment=segment, verify_attribute=lambda *_: True))
    frame = SimpleNamespace(frame_path=str(path), crop_path=str(path), diff_bbox=[0, 0, 100, 100])
    assert len(verify_frame(frame, "dog with a red collar")) == 1
    assert prompts == ["dog"]


# -- explicit clip selection ---------------------------------------------------

def test_selected_clip_never_mixes_with_newer_clip(isolated_env):
    _insert("old-keys", 1.0, "desk_frame_01.jpg", ["keys"], clip="old-clip")
    _insert("new-mug", 9.0, "desk_frame_unsure.jpg", ["mug"], clip="new-clip")
    result = query_memory("keys", clip_id="old-clip")
    assert result.state == "FOUND_NOW"
    assert result.clip_id == "old-clip"
    assert result.frame_id == "old-keys"
    assert all(item.frame_id == "old-keys" for item in result.trail)
    assert "Selected clip" in result.search.scope


def test_unknown_clip_is_unsure_without_searching_others(isolated_env):
    _insert("frame-1", 1.0, "desk_frame_01.jpg", ["keys"])
    result = query_memory("keys", clip_id="no-such-clip")
    assert result.state == "UNSURE"
    assert result.clip_id == "no-such-clip"
    assert result.search.frames_checked == 0


def test_same_query_is_scoped_per_clip_in_snapshots(isolated_env):
    _insert("a-keys", 1.0, "desk_frame_01.jpg", ["keys"], clip="clip-a")
    _insert("b-keys", 1.0, "desk_frame_01.jpg", ["keys"], clip="clip-b")
    assert query_memory("keys", clip_id="clip-a").frame_id == "a-keys"
    assert query_memory("keys", clip_id="clip-b").frame_id == "b-keys"


# -- temporal search: first seen, budgets, recent-first ------------------------

def test_first_seen_returns_earliest_verified(isolated_env, monkeypatch):
    for index in range(6):
        _insert(f"f{index}", float(index), "unknown.jpg", ["water"])
    monkeypatch.setattr("core.query_service.get_model_client",
                        lambda: SimpleNamespace(normalize_query=lambda _: "keys",
                                                describe_spatial=lambda *a: None))
    monkeypatch.setattr("core.query_service.verify_frame",
                        lambda frame, _: [Detection(.95, [1, 2, 30, 40])] if frame.timestamp >= 3 else [])
    result = query_memory("When did the keys first appear?")
    assert result.state == "FOUND_NOW"
    assert result.last_seen_seconds == 3
    assert result.last_seen_interval == [2, 3]


def test_budget_exhaustion_reports_partial_search(isolated_env, monkeypatch):
    get_settings().query_max_frame_checks = 3
    for index in range(10):
        _insert(f"f{index}", float(index), "unknown.jpg", ["water"])
    monkeypatch.setattr("core.query_service.get_model_client",
                        lambda: SimpleNamespace(normalize_query=lambda _: "keys"))
    monkeypatch.setattr("core.query_service.verify_frame", lambda frame, _: [])
    result = query_memory("When were the keys last seen?")
    assert result.state == "UNSURE"
    assert result.search.budget_exhausted is True
    assert result.search.complete is False
    assert result.search.frames_checked == 3
    assert "not evidence of absence" in result.answer


def test_last_seen_stops_after_newest_positive_batch(isolated_env, monkeypatch):
    for index in range(15):
        _insert(f"f{index}", float(index), "unknown.jpg", ["water"])
    checked = []
    def verify(frame, _):
        checked.append(frame.timestamp)
        return [Detection(.95, [1, 2, 30, 40])] if frame.timestamp == 14 else []
    monkeypatch.setattr("core.query_service.get_model_client",
                        lambda: SimpleNamespace(normalize_query=lambda _: "keys"))
    monkeypatch.setattr("core.query_service.verify_frame", verify)
    result = query_memory("When were the keys last seen?")
    assert result.last_seen_seconds == 14
    assert len(checked) <= get_settings().parallel_candidate_count


def test_moved_question_with_single_sighting_is_unsure(isolated_env):
    _insert("only", 1.0, "desk_frame_01.jpg", ["reading glasses"])
    result = query_memory("Did the reading glasses move?")
    assert result.state == "UNSURE"
    assert result.movement.status == "unknown"


# -- evidence reuse --------------------------------------------------------------

def test_second_query_reuses_stored_sighting(isolated_env, monkeypatch):
    _insert("frame-1", 1.0, "desk_frame_01.jpg", ["keys"])
    first = query_memory("keys")
    assert first.state == "FOUND_NOW"

    def forbidden(frame, _):
        raise AssertionError("verify_frame should not run for a frame with stored evidence")
    monkeypatch.setattr("core.query_service.verify_frame", forbidden)
    second = query_memory("keys")
    assert second.state == "FOUND_NOW"
    assert second.search.evidence_reused >= 1
    assert second.search.model_calls == 0  # stored sighting + cached calls only


# -- last-seen refinement --------------------------------------------------------

def _write_video(path, seconds=5, fps=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (96, 64))
    assert writer.isOpened()
    frame = np.full((64, 96, 3), 127, dtype=np.uint8)
    for _ in range(seconds * fps):
        writer.write(frame)
    writer.release()


def test_last_seen_refines_between_samples(isolated_env, tmp_path, monkeypatch):
    video = tmp_path / "clip.avi"
    _write_video(video)
    upsert_clip("desk-01", source_path=str(video), status="ready")
    for ts in (0.0, 2.0, 4.0):
        _insert(f"f{ts}", ts, "unknown.jpg", ["water"])
    monkeypatch.setattr("core.query_service.get_model_client",
                        lambda: SimpleNamespace(normalize_query=lambda _: "keys"))
    monkeypatch.setattr("core.query_service.verify_frame",
                        lambda frame, _: [Detection(.95, [1, 2, 30, 40])] if 2 <= frame.timestamp <= 3.0 else [])
    result = query_memory("When were the keys last seen?")
    assert result.last_seen_seconds == 3.0
    assert result.search.refined is True
    assert result.last_seen_interval[0] == 3.0
    assert result.last_seen_interval[1] < 4.0
    conn = sqlite3.connect(get_settings().db_path)
    refined = conn.execute("SELECT COUNT(*) FROM frames WHERE sampling_reason='refinement'").fetchone()[0]
    conn.close()
    assert refined >= 1


# -- indexing states: partial, failed, retry --------------------------------------

def _write_static_clip(path, frame_count=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 3, (96, 64))
    assert writer.isOpened()
    frame = np.full((64, 96, 3), 127, dtype=np.uint8)
    for _ in range(frame_count):
        writer.write(frame)
    writer.release()


def test_partial_index_and_safe_retry(isolated_env, tmp_path, monkeypatch):
    import core.vlm_client as vlm_client
    clip = tmp_path / "static.avi"
    _write_static_clip(clip)
    original = vlm_client.index_settled_frame
    def flaky(clip_id, timestamp, *args, **kwargs):
        if timestamp == 2.0:
            raise RuntimeError("provider unavailable for one frame")
        return original(clip_id, timestamp, *args, **kwargs)
    monkeypatch.setattr(vlm_client, "index_settled_frame", flaky)

    indexed = process_video(clip, "partial-01")
    row = get_clip("partial-01")
    assert row["status"] == "partial"
    assert row["failed_frame_count"] == 1
    assert [item["timestamp"] for item in indexed] == [0.0]

    monkeypatch.setattr(vlm_client, "index_settled_frame", original)
    retried = process_video(clip, "partial-01")
    row = get_clip("partial-01")
    assert row["status"] == "ready"
    assert sorted(item["timestamp"] for item in retried) == [0.0, 2.0]
    conn = sqlite3.connect(get_settings().db_path)
    count = conn.execute("SELECT COUNT(*) FROM frames WHERE clip_id='partial-01'").fetchone()[0]
    conn.close()
    assert count == 2  # retry reused the stored 0.0s frame instead of duplicating it

    with pytest.raises(ValueError, match="already exists"):
        process_video(clip, "partial-01")


def test_pan_does_not_flood_scene_change_samples(isolated_env, tmp_path):
    # A textured pattern translating every frame is a camera pan, not a new
    # scene every sampled instant.
    rng = np.random.default_rng(7)
    canvas = rng.integers(0, 255, (128, 400, 3), dtype=np.uint8)
    path = tmp_path / "pan.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 3, (96, 64))
    assert writer.isOpened()
    for index in range(12):
        writer.write(canvas[32:96, index * 8:index * 8 + 96].copy())
    writer.release()
    settings = get_settings()
    settings.scene_change_threshold = 1
    settings.scene_change_min_interval_seconds = 0.1

    indexed = process_video(path, "pan-01")
    reasons = [item["sampling_reason"] for item in indexed]
    assert "scene_change" not in reasons
    assert reasons  # periodic coverage still exists


def test_api_exposes_clips_and_accepts_selection(isolated_env):
    from main import QueryRequest, list_indexed_clips
    from main import query_memory as query_endpoint
    _insert("frame-1", 1.0, "desk_frame_01.jpg", ["keys"])
    upsert_clip("desk-01", source_path="video.mp4", status="ready", frame_count=1)
    clips = list_indexed_clips()["clips"]
    assert clips[0]["clip_id"] == "desk-01"
    assert clips[0]["status"] == "ready"
    result = query_endpoint(QueryRequest(query="keys", clip_id="desk-01"))
    assert result.state == "FOUND_NOW"
    assert result.clip_id == "desk-01"
