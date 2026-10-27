from fastapi import FastAPI, HTTPException
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
    # TODO (Days 2-3): Connect this to core.keyframer.process_video and core.vlm_client
    return {"status": "processing", "clip_id": req.clip_id, "message": "Indexing started."}

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