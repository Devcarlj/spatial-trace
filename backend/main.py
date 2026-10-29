from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from contextlib import asynccontextmanager
from database import init_db

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

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "SpatialTrace backend is running."}

@app.post("/api/index")
async def index_video(req: IndexRequest):
    """
    Triggers the Index Time pipeline: Frame Sampler -> Settle Detector -> Region Diff -> VLM -> SQLite[cite: 1].
    """
    from core.keyframer import process_video

    try:
        frames = await run_in_threadpool(process_video, req.video_path, req.clip_id)
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
    """
    Triggers the Query Time pipeline: LLM Normalizer -> SQLite Text Match -> SAM 3.1 -> Spatial LLM -> UI State[cite: 1].
    """
    # TODO (Days 2-3): Connect to query normalizer, SQLite search, and SAM client
    return {
        "query": req.query,
        "state": "UNSURE", # Placeholder for FOUND_NOW, MOVED, or UNSURE[cite: 1]
        "message": "Query endpoint scaffolded."
    }

if __name__ == "__main__":
    import uvicorn
    # Run the server: python main.py
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
