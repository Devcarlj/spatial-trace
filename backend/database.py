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
        CREATE TABLE IF NOT EXISTS clips (
            clip_id TEXT PRIMARY KEY,
            source_path TEXT,
            status TEXT NOT NULL DEFAULT 'indexing',
            frame_count INTEGER NOT NULL DEFAULT 0,
            failed_frame_count INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    # Additive migrations for existing local databases.
    frame_columns = {row[1] for row in cursor.execute("PRAGMA table_info(frames)")}
    if "sampling_reason" not in frame_columns:
        cursor.execute("ALTER TABLE frames ADD COLUMN sampling_reason TEXT")
    sighting_columns = {row[1] for row in cursor.execute("PRAGMA table_info(sightings)")}
    for column in ("track_id", "tracking_json"):
        if column not in sighting_columns:
            cursor.execute(f"ALTER TABLE sightings ADD COLUMN {column} TEXT")

    conn.commit()
    conn.close()


CLIP_STATUSES = {"indexing", "ready", "partial", "failed"}


def upsert_clip(clip_id, source_path=None, status=None, frame_count=None,
                failed_frame_count=None, error=None):
    """Create/update a clip row; only explicitly passed fields change."""
    if status is not None and status not in CLIP_STATUSES:
        raise ValueError(f"Unknown clip status: {status}")
    path = get_db_path()
    init_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO clips (clip_id, source_path, status) VALUES (?, ?, 'indexing') "
            "ON CONFLICT(clip_id) DO NOTHING",
            (clip_id, source_path),
        )
        assignments, params = [], []
        for column, value in (("source_path", source_path), ("status", status),
                              ("frame_count", frame_count),
                              ("failed_frame_count", failed_frame_count), ("error", error)):
            if value is not None:
                assignments.append(f"{column} = ?")
                params.append(value)
        if assignments:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
            conn.execute(f"UPDATE clips SET {', '.join(assignments)} WHERE clip_id = ?",
                         (*params, clip_id))
        conn.commit()
    finally:
        conn.close()
    return get_clip(clip_id)


def get_clip(clip_id):
    path = get_db_path()
    init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM clips WHERE clip_id = ?", (clip_id,)).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def list_clips():
    path = get_db_path()
    init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM clips ORDER BY updated_at DESC, clip_id").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


# Back-compat for imports that still read DB_PATH at module load.
DB_PATH = "data/spatialtrace.db"


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
