import sqlite3
import pytest
from fastapi import HTTPException
from main import frame_image
from core.settings import get_settings

def test_frame_endpoint_serves_only_indexed_frame_root(isolated_env):
    frame = isolated_env / "frames" / "clip" / "frame.jpg"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"jpeg")
    outside = isolated_env / "secret.jpg"
    outside.write_bytes(b"private")
    conn = sqlite3.connect(get_settings().db_path)
    conn.executemany("INSERT INTO frames (id,frame_path) VALUES (?,?)",
                     [("safe", str(frame)), ("outside", str(outside))])
    conn.commit()
    conn.close()
    assert frame_image("safe").path == frame.resolve()
    for key in ["outside", "unknown"]:
        with pytest.raises(HTTPException) as error:
            frame_image(key)
        assert error.value.status_code == 404
