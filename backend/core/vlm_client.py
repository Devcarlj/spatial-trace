import json
import sqlite3
import uuid

from core.providers import get_model_client
from database import get_db_path, init_db


def call_cheap_vlm(crop_path):
    """
    Cheap VLM via ModelClient: schema validation, one retry, then cache.
    """
    result = get_model_client().vlm_describe(crop_path)
    return result.model_dump()


def index_settled_frame(clip_id, timestamp, frame_path, crop_path, diff_bbox):
    """
    Writes the processed keyframe data to SQLite.
    """
    vlm_result = call_cheap_vlm(crop_path)

    db_path = get_db_path()
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    frame_id = str(uuid.uuid4())
    objects_json = json.dumps(vlm_result["objects"])
    diff_bbox_json = json.dumps(diff_bbox)

    cursor.execute('''
        INSERT INTO frames (id, clip_id, ts, frame_path, crop_path, diff_bbox, caption, objects_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (frame_id, clip_id, timestamp, frame_path, crop_path, diff_bbox_json, vlm_result["caption"], objects_json))

    conn.commit()
    conn.close()
    print(f"Indexed frame {frame_id} for clip {clip_id}")
    return frame_id
