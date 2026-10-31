from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from database import init_db
from pathlib import Path
import sqlite3
import logging
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from core.settings import get_settings
from core.live_transport import ProviderUnavailable

# Pydantic models for incoming requests
class QueryRequest(BaseModel):
    query: str = Field(max_length=200)
    clip_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")

class IndexRequest(BaseModel):
    video_path: str = Field(min_length=1, max_length=2048)
    clip_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


def dependency_error(exc: ImportError) -> str:
    return (f"Backend dependency {exc.name or 'unknown'} could not load. "
            "Start the backend with backend/run.ps1, or install backend/requirements.txt "
            "in the Python environment running the server.")


# Lifecycle manager to initialize DB on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Health must not report success when the request pipelines cannot even load.
    try:
        from core.keyframer import process_video
        from core.query_service import query_memory
    except ImportError as exc:
        raise RuntimeError(dependency_error(exc)) from exc
    # Initialize the SQLite schema on startup
    init_db()
    yield
    # Cleanup if needed

app = FastAPI(title="SpatialTrace v2 API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "SpatialTrace backend is running.", "mode": get_settings().spatialtrace_mode}

@app.get("/api/frames/{frame_id}")
def frame_image(frame_id: str):
    conn = sqlite3.connect(get_settings().db_path)
    try:
        row = conn.execute("SELECT frame_path FROM frames WHERE id=?", (frame_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Frame not found")
    path = Path(row[0]).resolve()
    root = (get_settings().data_dir / "frames").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Frame unavailable")
    return FileResponse(path, media_type="image/jpeg")

@app.get("/api/clips")
def list_indexed_clips():
    """Clips with explicit indexing state: indexing/ready/partial/failed."""
    from database import list_clips
    return {"clips": list_clips()}


@app.post("/api/index")
def index_video(req: IndexRequest):
    """
    Sample recorded footage and index its observed regions.
    """
    try:
        from core.keyframer import process_video
        frames = process_video(req.video_path, req.clip_id)
    except ImportError as exc:
        logging.exception("Indexing dependencies unavailable")
        raise HTTPException(status_code=500, detail=dependency_error(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logging.exception("Indexing failed")
        raise HTTPException(status_code=500, detail="Indexing failed. Check the backend logs and retry with a new clip name.") from exc
    from database import get_clip
    clip = get_clip(req.clip_id) or {}
    status = clip.get("status", "ready")
    return {
        "status": status,
        "clip_id": req.clip_id,
        "indexed_frame_count": len(frames),
        "failed_frame_count": clip.get("failed_frame_count", 0),
        "retryable": status in {"partial", "failed"},
        "frames": frames,
    }

@app.post("/api/query")
def query_memory(req: QueryRequest):
    """Search indexed clips and visually verify the requested item."""
    try:
        from core.query_service import query_memory as run_query
        result = run_query(req.query, req.clip_id)
        if result.frame_id:
            result.frame_url = f"/api/frames/{result.frame_id}"
        for item in result.trail:
            item.frame_url = f"/api/frames/{item.frame_id}"
        return result
    except ImportError as exc:
        logging.exception("Query dependencies unavailable")
        raise HTTPException(status_code=500, detail=dependency_error(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logging.exception("Query failed")
        raise HTTPException(status_code=500, detail="Query failed. Check the backend logs and try again.") from exc

if __name__ == "__main__":
    import uvicorn
    # Run the server: python main.py
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
