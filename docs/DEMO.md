# Repeatable synthetic demo

Use an isolated data directory so fixture sightings never mix with live footage.
These are scripted model fixtures, not a benchmark of live model accuracy.

From `backend/`, with the Python environment activated:

```powershell
$env:SPATIALTRACE_MODE='mock'
$env:OFFLINE_SNAPSHOTS='0'
$env:SPATIALTRACE_DATA_DIR=Join-Path (Get-Location) 'data/synthetic-demo'
python demo.py
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

In another terminal, from `frontend/`:

```powershell
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open http://127.0.0.1:3000 and search:

1. `keys`: FOUND_NOW, two associated observations with small positional jitter.
2. `where are my specs`: MOVED, the glasses change position on a stable background.
   Select each timestamp to inspect its own mask. Toggle the box off to see the
   exact glasses silhouette, and try 200% zoom.
3. `mug`: UNSURE, with a 0.51 model score and possible evidence. A mask alone does
   not promote a detection to a confirmed sighting.

The generator writes a manifest, five PNG stills, three reference AVI clips, and
three query snapshots below the chosen data directory. It seeds the stills through
the indexing metadata writer. The reference AVI files document the synthetic scene;
re-indexing those clips in mock mode does not reproduce filename-keyed detections.
Use normal index → query with live mode to evaluate model accuracy on videos.

To replay without any provider calls, restart the backend with the same data
directory and `OFFLINE_SNAPSHOTS=1`. Search the exact phrases above. The snapshots
include decoded overlays and movement metadata; keep their referenced frame files.
Regenerating the fixture is idempotent and does not duplicate its frame rows.

The regression suite additionally exercises camera pan/rotation/zoom, scene cuts,
untextured backgrounds, multiple instances, missing observations, large time gaps,
small-object recovery, source-coordinate scaling, and malformed mask fallback.
