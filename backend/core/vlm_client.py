import sqlite3
import uuid
import json

DB_PATH = "data/spatialtrace.db"

def call_cheap_vlm(crop_path):
    """
    Calls a cheap VLM via the hackathon API[cite: 1].
    Must output strict JSON schema: {"objects": ["item1", "item2"], "caption": "..."}[cite: 1].
    Needs schema validation and 1 retry on failure[cite: 1].
    """
    # TODO: Implement actual VLM HTTP call and schema validation (e.g., using Pydantic)
    return {
        "objects": ["keys", "black sunglasses", "book"],
        "caption": "A pair of black sunglasses and keys resting on a wooden desk."
    }

def index_settled_frame(clip_id, timestamp, frame_path, crop_path, diff_bbox):
    """
    Writes the processed keyframe data to SQLite[cite: 1].
    """
    # Call VLM to get caption and noun list[cite: 1]
    vlm_result = call_cheap_vlm(crop_path)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    frame_id = str(uuid.uuid4())
    objects_json = json.dumps(vlm_result["objects"])
    diff_bbox_json = json.dumps(diff_bbox)
    
    # Store frames, timestamp, objects array, caption, diff_bbox, and file paths[cite: 1]
    cursor.execute('''
        INSERT INTO frames (id, clip_id, ts, frame_path, crop_path, diff_bbox, caption, objects_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (frame_id, clip_id, timestamp, frame_path, crop_path, diff_bbox_json, vlm_result["caption"], objects_json))
    
    conn.commit()
    conn.close()
    print(f"Indexed frame {frame_id} for clip {clip_id}")