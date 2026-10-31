# SpatialTrace implementation status

Updated: 2026-10-31. Scope: current local working tree, including uncommitted
changes. Follow the [roadmap](IMPLEMENTATION_PLAN.md) for ordered work and criteria.

## Implemented capabilities

- Live Meta Responses adapters for vision/text and streamed SAM segmentation,
  image payloads, explicit confidence parsing, and provider-error handling.
- FastAPI/Next.js index → query → evidence workflow, CLI, SQLite sightings,
  model/content-isolated caches, and offline snapshots.
- Full frames every two seconds, significant visual changes, settled-motion
  crops, and same-timestamp sampling deduplication.
- Ordinary text retrieval with context/fallback, parallel verification, and
  contextual zoom/full-frame/overlapping-tile recovery.
- Last-seen queries scan the newest clip's indexed observations and return a
  latest verified sample timestamp, rather than an exact exit time.
- Two-stage person/clothing verification for normalized `person wearing ...`
  and `person in ...` phrases; unclear attributes fail closed.
- Query-local appearance/size/geometry association, camera-motion compensation,
  movement tolerances, and conservative handling of gaps/ambiguity.
- Pixel masks, boxes, per-sighting images, timestamps, scores, recovery labels,
  zoom, loading/errors, and image-failure handling in the UI.
- Scripted FOUND_NOW/MOVED/UNSURE demos and offline replay.
- Startup dependency checks, Windows launcher, input limits, protected clip
  names, and atomic cache/artifact publishing.

## Recorded validation

- Latest backend run: **69 tests passed**, including detection/mask metrics,
  duplicate predictions, missing samples, and false-movement controls alongside
  temporal search, attributes, recovery, tracking, transport, masks, and APIs.
- Earlier TypeScript, ESLint, production build, and desktop/narrow browser checks
  passed; those checks predate the latest backend temporal/attribute changes.
- Public surveillance-video live smoke verified indexing, person detection,
  and HTTP-served evidence.
- User coastal recording: first coverage run saved 40 rows versus one fallback
  frame. That run preceded deduplication, so 40 is not a count of unique samples
  produced by the finalized sampler.
- Initial live cases: blue vest found at 8.00s with box IoU 0.9484; blue shirt
  returned UNSURE. Latencies: 92.94s and 31.38s with caches enabled. See
  [results](../backend/evaluation/RESULTS.md).

- Expanded baseline: 30 source samples reviewed across the full 28.5s duration;
  five labeled target/frame checks, two positive person boxes, three negatives.
  Detection TP=2, FP=0, FN=0; matched box IoU mean 0.9390; sample coverage 5/5.
  Two HTTP queries pass; mean latency 14.03s with caches in use (not a cold run).
  Mask IoU and false movement remain unmeasured because labels are missing.
- During this run the frontend returned HTTP 500 because the backend had stopped.
  Starting backend/run.ps1 restored health and both end-to-end query cases.

Source review is at one-second intervals plus the last frame, not every frame.
The shirt-negative remains provisional for distant garments/unsampled instants.
Independent human review and finer exit-boundary annotation remain. Synthetic
tests and this small calibration sample do not establish broad accuracy.

## Partial and missing work

- Labels: one supplemental outdoor recording, 30 reviewed source frames, five
  labeled target/frame checks. Since 2026-10-31 the six desk scenarios have
  openly-licensed online substitute clips (Mixkit) with agent-reviewed samples
  and movement labels; four are calibration and two held-out (see
  backend/evaluation/ONLINE_SOURCES.md). Masks, independent human review, and
  indexing/evaluator runs for these clips remain missing, and stock clips only
  partly match the capture guide's scripted actions.
- Evaluation: detection precision/recall, box/mask IoU, false movement, temporal
  error, uncertainty, exact-sample coverage, and latency are implemented. Reports
  retain provenance, declared cache state, settings, evidence, and errors.
  Mask/movement measurements await labels; held-out calibration remains.
- Search: newest-clip scope for last-seen; limited candidates for ordinary queries.
  Explicit clip selection and general intent/attributes remain. The UI footer's
  all-clips wording needs alignment.
- Performance: last-seen currently verifies all unique samples before selecting
  the latest positive. Per-query workers are bounded; overall job/call/resource
  budgets are incomplete. Long operations still block the user's workflow.
- Sampling: camera pans can over-trigger visual differences; short appearances
  between samples can be missed. Failed indexes can leave partial evidence with
  no readiness model or resumable retry workflow.
- Tracking: persistent identity, explicit lost/re-acquired states, occlusion/
  re-entry association, and broad calibration remain.
- Review: detailed reasons, attribute explanations, side-by-side movement,
  correction flags, and clip library remain.
- Operations: background jobs, progress/cancellation, retention, storage cleanup,
  and resource limits remain. Public-hosting access controls are absent.

## Next action

Independently human-review the six online-scenario manifests in
backend/evaluation (footage and agent labels were added 2026-10-31), add mask
labels where feasible, index each clip and run the expanded evaluator per
manifest, then finish fine exit-boundary review on the supplemental recording.
Milestone 1 remains incomplete until those data requirements are met. See
[milestone 1](IMPLEMENTATION_PLAN.md#milestone-1--establish-the-real-video-baseline-next).
