from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from database import init_db
from pathlib import Path
import sqlite3
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from core.settings import get_settings
from core.live_transport import ProviderUnavailable

# Pydantic models for incoming requests
class QueryRequest(BaseModel):
    query: str

class IndexRequest(BaseModel):
    video_path: str
    clip_id: str

# Lifecycle manager to initialize DB on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
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

@app.post("/api/index")
async def index_video(req: IndexRequest):
    """
    Triggers the Index Time pipeline: Frame Sampler -> Settle Detector -> Region Diff -> VLM -> SQLite[cite: 1].
    """
    from core.keyframer import process_video

    try:
        frames = process_video(req.video_path, req.clip_id)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc
    return {
        "status": "completed",
        "clip_id": req.clip_id,
        "indexed_frame_count": len(frames),
        "frames": frames,
    }

@app.post("/api/query")
async def query_memory(req: QueryRequest):
    """Search indexed clips and visually verify the requested item."""
    from core.query_service import query_memory as run_query

    try:
        result = run_query(req.query)
        if result.frame_id:
            result.frame_url = f"/api/frames/{result.frame_id}"
        for item in result.trail:
            item.frame_url = f"/api/frames/{item.frame_id}"
        return result
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc

if __name__ == "__main__":
    import uvicorn
    # Run the server: python main.py
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
