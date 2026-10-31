# SpatialTrace

Index a local video and find an object in its recorded frames. FastAPI runs the
frame sampler, vision indexing, SQLite retrieval, and SAM verification. Next.js
proxies the API and displays pixel masks, object boxes, and associated sightings.

## Run locally

Python 3.12+ and Node 20.9+ are required. One-time setup:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..\frontend
npm ci
```

Copy `backend/.env.example` to `backend/.env`. The default mock mode needs
no edits; set `MODEL_API_KEY` in `backend/.env` for live mode.

Then, from the repository root, start everything with one command:

```powershell
.\run.ps1              # or double-click run.bat
.\run.ps1 -Mode live   # optional: use the live model APIs
```

`run.ps1` opens the backend (FastAPI on port 8000, via `backend/run.ps1`)
and the frontend (Next.js on port 3000) in separate windows and opens
http://127.0.0.1:3000 in your browser. Close those two windows to stop the
servers.

Open the UI, enter an absolute video path on the backend machine and a
unique clip name, click **Index video**, then ask about an object. Existing
clip names are rejected to preserve their saved evidence. Model credentials
stay on the backend; these endpoints are for trusted local use, not public
hosting.

To run the servers manually instead, start
`python -m uvicorn main:app --host 127.0.0.1 --port 8000` in `backend/`
(or `.\backend\run.ps1` from the root, which also picks up `backend/.deps`)
and `npm run dev -- --hostname 127.0.0.1` in `frontend/`. If the UI says
"The backend could not complete this request," check the backend window -
a plain HTTP 500 can mean a missing runtime dependency; restart the backend
with `backend/run.ps1` so the right environment is used.

## Live provider contract

Meta uses `https://api.meta.ai/v1/responses` for vision, normalization, spatial
description, and SAM. `muse-spark-1.3` is the default vision/text model;
`sam-3.1` performs segmentation. `cheap-vlm` and `muse-spark` were invalid IDs.
Images are sent as base64 data URLs. SAM uses SSE with
`metadata.include_confidence="true"` and `mask_encoding="one_bit"`. Meta's pinned
`meta-sam-parser` codec decodes both one-bit and lossless mask tokens into PNG
overlays. Raw mask tokens are preserved. Inclusive wire boxes become half-open
internal boxes, scaled from provider image coordinates back to the original frame.
The UI supports independent mask/box toggles, 200% zoom, and per-sighting overlays.
Corrupt or legacy masks fall back to box evidence with an explicit UI notice.

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

Fixed-camera footage works best. The sampler saves a full frame every two seconds,
adds significant scene changes, and detects a motion spike followed by a calm
interval. This gives “last seen” queries temporal coverage while retaining focused
post-motion observations. Tune the periodic interval and scene-change thresholds
in `backend/.env`; each saved observation makes indexing slower and adds model cost.
`FOUND_NOW` means found in saved footage, never a current camera view.
Retrieval combines text matches with recent context from the newest matching clip,
and falls back to recent frames when captions do not match. Up to eight candidates
are checked by default, with five parallel workers.

Last-seen questions instead verify all unique indexed timestamps in the newest
clip. They return a latest verified sampled sighting, not an exact disappearance
time. Explicit clip selection is not yet available. Person/clothing phrases such
as `person wearing a blue vest` detect the person first, then visually check their
clothing. Attribute handling is currently limited to these person phrase patterns;
a detection score is not a calibrated probability that the attribute is correct.

Tracking anchors on the latest confident detection and associates older sightings
using masked color appearance, size, and position. Background ORB features and a
RANSAC similarity transform compensate for camera translation, rotation, and zoom.
Movement must exceed both a 12px floor and 15% of the object's diagonal. Weak
background alignment, ambiguous lookalikes, an intervening non-detection, or gaps
over 30 seconds suppress identity/movement claims. Track IDs are query-local,
stored with sightings; they are not persistent SAM video IDs. Scene cuts and
strong parallax produce unknown movement when alignment fails. These heuristics
still need real-video calibration and cannot establish identity through occlusion.

Weak or tiny detections trigger up to four extra SAM calls per frame: a contextual
zoom, a full-frame fallback when needed, then overlapping tiles. Coordinates and
masks map back to the full-resolution source. The call budget and thresholds are
configurable in `backend/.env.example`; set `RECOVERY_MAX_CALLS=0` to disable.
Recovery can increase latency and provider cost; an uncertain result stays uncertain
unless the rerun meets the confidence threshold. New caches use schema version 3
so older coordinate conventions are not replayed as current provider results.

Successful query responses are recorded under `data/snapshots/`. Set
`OFFLINE_SNAPSHOTS=1` to replay the exact query without model calls. Preserve
the associated frame files and database. Missing snapshots return UNSURE.
Mock mode is deterministic for fixture filenames; arbitrary videos do not get
fabricated high-confidence detections.

For a repeatable, credential-free demonstration, see [the demo guide](docs/DEMO.md).
It generates stills, reference clips, and offline snapshots for FOUND_NOW, MOVED,
and UNSURE, including actual non-rectangular masks.

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

The tracked [roadmap](docs/IMPLEMENTATION_PLAN.md) defines priorities and completion
criteria, superseding the old locally ignored plan under `.agents/`.
[Implementation status](docs/IMPLEMENTATION_STATUS.md) records capabilities,
validation, and gaps. The [evaluation guide](backend/evaluation/README.md) explains
the initial live cases and their limitations. This is still a trusted
local application: public deployment needs authentication, background jobs,
retention limits, and broader resource/concurrency controls. Long model calls run
in FastAPI's worker pool; the Next.js proxy allows up to ten minutes per request.
