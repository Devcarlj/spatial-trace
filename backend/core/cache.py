"""Shared API cache: SQLite `api_cache` plus `data/cache/<key>.json`."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from core.settings import get_settings
from core.files import atomic_write
from database import init_db


def cache_key(endpoint: str, payload: Any) -> str:
    settings = get_settings()
    images = {key: hashlib.sha256(Path(value).read_bytes()).hexdigest()
              for key, value in payload.items()
              if key in {"image_path", "crop_path"} and Path(value).is_file()} if isinstance(payload, dict) else {}
    blob = json.dumps({"endpoint": endpoint, "payload": payload, "images": images,
                       "mode": settings.spatialtrace_mode, "base": settings.sam_base_url,
                       "models": [settings.sam_model_name, settings.vlm_model_name, settings.llm_model_name],
                       "version": 3}, sort_keys=True, default=str)  # half-open boxes + source dimensions
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    init_db(settings.db_path)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _disk_path(key: str) -> Path:
    settings = get_settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    return settings.cache_dir / f"{key}.json"


def get_cached(key: str) -> Any | None:
    disk = _disk_path(key)
    if disk.exists():
        try:
            return json.loads(disk.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # Recover legacy partial files from the SQLite copy.

    conn = _connect()
    try:
        row = conn.execute("SELECT response_json FROM api_cache WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    data = json.loads(row["response_json"])
    atomic_write(disk, json.dumps(data))
    return data


def set_cached(key: str, data: Any) -> None:
    encoded = json.dumps(data)
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO api_cache (key, response_json) VALUES (?, ?)",
            (key, encoded),
        )
        conn.commit()
    finally:
        conn.close()
    atomic_write(_disk_path(key), encoded)


def cached_call(endpoint: str, payload: Any, fn) -> Any:
    key = cache_key(endpoint, payload)
    hit = get_cached(key)
    if hit is not None:
        from core.budget import count_cache_reuse
        count_cache_reuse()
        return hit
    from core.budget import count_model_call
    count_model_call()
    result = fn()
    set_cached(key, result)
    return result
