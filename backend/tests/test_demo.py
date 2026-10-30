import sqlite3

from core.query_service import query_memory
from core.settings import get_settings
from demo import generate_demo


def test_scripted_demo_exercises_masks_tracking_snapshots_and_persistence(isolated_env, monkeypatch):
    manifest = generate_demo()
    assert [item["state"] for item in manifest["scenarios"].values()] == ["FOUND_NOW", "MOVED", "UNSURE"]
    moved = query_memory("where are my specs")
    assert moved.movement.status == "moved"
    assert len(moved.trail) == 2
    assert all(hit.mask_overlay and hit.track_id == moved.track_id for hit in moved.trail)
    with sqlite3.connect(get_settings().db_path) as conn:
        rows = conn.execute("SELECT track_id,tracking_json FROM sightings WHERE query_label='reading glasses'").fetchall()
        assert len(rows) == 2
        assert all(row[0] == moved.track_id and '"status":"moved"' in row[1] for row in rows)
    get_settings().offline_snapshots = True
    monkeypatch.setattr("core.query_service.get_model_client", lambda: (_ for _ in ()).throw(AssertionError("Offline must not call models")))
    assert query_memory("where are my specs") == moved


def test_unmentioned_intervening_frame_breaks_track(isolated_env):
    generate_demo()
    get_settings().recovery_max_calls = 0
    with sqlite3.connect(get_settings().db_path) as conn:
        conn.execute("""INSERT INTO frames (id,clip_id,ts,frame_path,crop_path,diff_bbox,caption,objects_json)
                        SELECT 'occluded',clip_id,2,frame_path,'unknown.jpg',diff_bbox,'A desk', '["book"]'
                        FROM frames WHERE clip_id='synthetic-glasses' LIMIT 1""")
    result = query_memory("where are my specs")
    assert result.state == "FOUND_NOW"
    assert result.movement.status == "unknown"
    assert "occlusion" in result.movement.reason
    assert len(result.trail) == 1
