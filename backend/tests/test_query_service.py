import json
import sqlite3

from core.query_service import query_memory, retrieve_frames
from core.settings import get_settings
from database import init_db


def _insert_frame(frame_id, ts, crop_path, objects, diff_bbox=(10, 20, 600, 400)):
    db_path = get_settings().db_path
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO frames (id, clip_id, ts, frame_path, crop_path, diff_bbox, caption, objects_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                frame_id,
                "desk-01",
                ts,
                f"frames/{frame_id}.jpg",
                crop_path,
                json.dumps(diff_bbox),
                f"A scene containing {', '.join(objects)}.",
                json.dumps(objects),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_query_retrieves_and_verifies_indexed_item(isolated_env):
    _insert_frame("frame-1", 1.0, "desk_frame_01.jpg", ["keys"])

    result = query_memory("keys")

    assert result.state == "FOUND_NOW"
    assert result.frame_id == "frame-1"
    assert result.bbox == [50.0, 220.0, 100.0, 260.0]
    assert result.trail[0].score == 0.88


def test_query_normalizes_synonym_and_reports_movement(isolated_env):
    _insert_frame("frame-old", 1.0, "desk_frame_01.jpg", ["reading glasses"])
    _insert_frame("frame-new", 2.0, "desk_frame_moved.jpg", ["reading glasses"], (100, 20, 600, 400))

    result = query_memory("where are my specs")

    assert result.state == "MOVED"
    assert result.frame_id == "frame-new"
    assert [item.frame_id for item in result.trail] == ["frame-old", "frame-new"]


def test_query_returns_unsure_when_index_has_no_match(isolated_env):
    _insert_frame("frame-1", 1.0, "desk_frame_01.jpg", ["keys"])

    result = query_memory("mug")

    assert result.state == "UNSURE"
    assert result.trail == []
    assert retrieve_frames("mug") == []
