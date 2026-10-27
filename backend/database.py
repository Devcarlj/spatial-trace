import sqlite3
import os

DB_PATH = "data/spatialtrace.db"

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # frames table[cite: 1]
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

    # sightings table (query-time results cache)[cite: 1]
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

    # api_cache table (mirrored to disk)[cite: 1]
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_cache (
            key TEXT PRIMARY KEY,
            response_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == "__main__":
    init_db()