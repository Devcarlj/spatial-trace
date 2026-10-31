# Real-video baseline

Milestone 1 is in progress. [dataset.json](dataset.json) lists the six required
desk scenarios; since 2026-10-31 each has an openly-licensed online substitute
clip with agent-reviewed sample labels (see [ONLINE_SOURCES.md](ONLINE_SOURCES.md)),
but none is complete: independent human review, indexing, and evaluator runs
remain. The existing outdoor recording is supplemental calibration footage.
See [CAPTURE_GUIDE.md](CAPTURE_GUIDE.md) for
recording/labeling, [RESULTS.md](RESULTS.md) for measurements, and the
[roadmap](../../docs/IMPLEMENTATION_PLAN.md) for completion criteria.

Run from backend in PowerShell with the frontend and backend running:

    $env:PYTHONPATH=(Resolve-Path .deps).Path # only for the existing .deps setup
    & .venv/Scripts/python.exe evaluate.py evaluation/blue_clothing.json --samples --cache-state mixed --output data/evaluation/baseline.json

HTTP queries exercise the frontend proxy at port 3000. --url can point to port
8000 to test the backend alone. --samples additionally calls local verification
on exact indexed timestamps; it may make paid provider calls with local model
settings. HTTP/server configuration is not introspected: use matching environments.
Reports record only non-secret settings, source/manifest hashes, git revision,
dirty state, declared cache state, per-case evidence/errors, and latencies.
A cold flag does not clear caches; declare it only after an isolated cold run.

Query metrics: right-clip/time/box pass rate, last-seen absolute error for returned
positive timestamps, uncertainty count, HTTP errors, mean request latency, and
false movement claims divided by annotated stationary cases. Check pass rate
alongside time error: missing/wrong-clip positives do not enter the error mean.
Expected movement must match the response status. Missing labels remain null.
Current cases have no movement labels.

Frame metrics measure candidates returned by local verify_frame, before final
query confidence/track decisions. One-to-one box matching at IoU >=0.5, precision TP/(TP+FP), recall
TP/(TP+FN), mean matched box IoU, mask IoU where full-frame PNG labels exist, and
evaluated/requested sample coverage. Duplicate predictions are false positives.
Mask misses or missing predicted masks score zero when a mask label exists.
Unlabeled masks stay null. Coverage means exact labeled timestamp availability
and successful verification, not the fraction of all video frames sampled.
Inspect errors to distinguish missing keyframes from provider/label errors.
Exit status is nonzero for failed queries, missing requested samples, or frame
false positives/negatives. Aggregate accuracy thresholds are not yet agreed.

Generate review artifacts without models or indexing:

    & .venv/Scripts/python.exe review_video.py "C:\path\clip.mp4" data/evaluation/review --interval 1

This writes full-resolution frames, timestamped contact sheets, and source SHA-256
metadata. The current recording has 30 reviewed source samples across 28.5s,
with full-resolution boxes at 4s and 8s. The blue vest is distinct from the white
shirt underneath. Shirt absence remains sample-based and provisional: distant
garments, unsampled instants, and exact exit timing require further review.

Last-seen searches all unique indexed samples in the newest clip. It can take
many provider calls. Clothing decomposition currently supports normalized person
wearing/in phrases only. These limits are milestone 2 work, not baseline claims.
