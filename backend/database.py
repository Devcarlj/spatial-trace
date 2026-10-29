import os
import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    from core.settings import get_settings

    return get_settings().db_path


def init_db(db_path: str | Path | None = None):
    path = Path(db_path) if db_path is not None else get_db_path()
    os.makedirs(path.parent, exist_ok=True)
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS frames (
            id TEXT PRIMARY KEY,
            clip_id TEXT,
            ts REAL,
            frame_path TEXT,
            crop_path TEXT,
            diff_bbox TEXT,
            caption TEXT,
            objects_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sightings (
            id TEXT PRIMARY KEY,
            frame_id TEXT,
            query_label TEXT,
            bbox TEXT,
            mask_path TEXT,
            score REAL,
            spatial_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (frame_id) REFERENCES frames (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_cache (
            key TEXT PRIMARY KEY,
            response_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_frames_clip_ts ON frames (clip_id, ts)')

    conn.commit()
    conn.close()


# Back-compat for imports that still read DB_PATH at module load.
DB_PATH = "data/spatialtrace.db"


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
