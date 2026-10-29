# SpatialTrace

Index a local video and find an object in its recorded frames. FastAPI runs the
frame sampler, vision indexing, SQLite retrieval, and SAM verification. Next.js
proxies the API and displays evidence with an object box and sighting trail.

## Run locally (two terminals)

Python 3.12+ and Node 20.9+ are required.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Copy .env.example to .env and configure MODEL_API_KEY for live mode.
$env:SPATIALTRACE_MODE='live'
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open http://127.0.0.1:3000. Enter an absolute video path on the backend machine
and a unique clip name, click **Index video**, then ask about an object.
The frontend uses same-origin `/api/index` and `/api/query`; set `BACKEND_URL`
before launching Next.js if the backend origin differs. Model credentials stay
on the backend. These endpoints are for trusted local use, not public hosting.

The local validation environment also has `backend/.deps/` with dependencies.
Set `PYTHONPATH` to its absolute path when using that environment instead of a venv.

## Live provider contract

Meta uses `https://api.meta.ai/v1/responses` for vision, normalization, spatial
description, and SAM. `muse-spark-1.3` is the default vision/text model;
`sam-3.1` performs segmentation. `cheap-vlm` and `muse-spark` were invalid IDs.
Images are sent as base64 data URLs. SAM uses SSE with
`metadata.include_confidence="true"`; its box/mask wire records are parsed into
the internal contract. The UI renders boxes; raw SAM mask tokens are preserved
in responses but pixel-mask decoding/rendering remains future work.

References: [vision](https://dev.meta.ai/docs/image-understanding),
[SAM requests](https://dev.meta.ai/docs/sam/segmenting),
[SAM output](https://dev.meta.ai/docs/sam/reading-segmentation).

```powershell
cd backend
$env:SPATIALTRACE_MODE='live'
python live_check.py path\to\image.jpg
python cli.py index path\to\video.mp4 unique-clip-name
python cli.py query "Where are the glasses?"
```

Provider failures return 502 with redacted model/status details. A provider 404
can mean an unavailable model or missing model access, not just a bad URL.
Network failures, incomplete streams, and missing confidence fail closed.
Caches separate mode, endpoint, models, and image content.

## Behavior and limits

Fixed-camera footage works best. The sampler detects a motion spike followed
by a calm interval. If nothing settles, it indexes the final sampled full frame;
this is a single observation, not comprehensive coverage of the video.
`FOUND_NOW` means found in saved footage, never a current camera view. Movement
compares coordinates within one clip; camera movement can produce false positives.
Retrieval falls back to recent frames when captions do not match. Confirmed
sightings are saved, with up to three returned in the trail.

Successful query responses are recorded under `data/snapshots/`. Set
`OFFLINE_SNAPSHOTS=1` to replay the exact query without model calls. Preserve
the associated frame files and database. Missing snapshots return UNSURE.
Mock mode is deterministic for fixture filenames; arbitrary videos do not get
fabricated high-confidence detections.

## Verification

```powershell
cd backend
python -m pytest -q
cd ../frontend
npx tsc --noEmit
npm run lint
npm run build
```

Live validation used OpenCV's public `samples/data/vtest.avi` (surveillance
footage): `/api/index` indexed one fallback frame and `/api/query` verified a
person with a bounding box. Model outputs can vary between calls.

The current roadmap is `.agents/docs/IMPLEMENTATION_PLAN.md` (locally ignored).
Scripted demo fixtures, pixel-mask overlays, crop reruns, and robust movement
tracking still need work; the roadmap must not mark those complete.
