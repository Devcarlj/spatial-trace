# Initial live evaluation — 2026-10-30

Manifest: `blue_clothing.json`. Newest indexed clip:
`blue-shirt-coverage-20261030-195136`.

- Blue vest: FOUND_NOW at 8.00s, box [223, 295, 478, 638], SAM score
  0.9766, box IoU 0.9484 against the manual sample label. Latency: 92.94s.
- Blue shirt: UNSURE, no timestamp or box. Latency: 31.38s.
- Initial checks: 2/2 passed. Mean latency: 62.16s. Existing caches were enabled;
  these timings are not a cold-cache benchmark.
- Backend suite: 62 tests passed.

## Expanded baseline — 2026-10-30

Source fingerprint and sample labels are in blue_clothing.json. Review artifacts
are under ignored backend/data/evaluation/coastal-review: 30 source frames at
0-28s whole-second intervals plus frame 854 (28.467s). Full-resolution positive
boxes were reviewed at 4s and 8s. Independent human review remains pending.

- Frame checks: 5/5 evaluated, TP=2, FP=0, FN=0. Precision=1.0 and recall=1.0
  on these two positives and three negatives only. Matched box IoU mean=0.938963.
- Mask IoU: unmeasured; both positive labels lack masks.
- False movement rate: unmeasured; neither query has a movement label.
- Frontend HTTP queries: 2/2 pass; vest at 8.00s (15.269s latency), shirt UNSURE
  (12.793s latency). Mean=14.031s. Cache state declared mixed; existing cache
  entries were in use. This is not a cold-cache benchmark or proven speedup.
- Last-seen absolute error=0 on the one returned positive timestamp relative to
  the sampled label. It does not measure exact exit time.
- Backend suite: 69 tests passed, including metric failure controls and ordinary
  movement cases without temporal labels.
- First HTTP run returned 500 because no backend listened on port 8000. Starting
  the project backend restored health and the full query check passed.

Raw report: backend/data/evaluation/baseline-20261030.json (local, ignored), with
manifest hash, revision/dirty state, settings, evidence, errors, and latencies.
See README.md for the reproducible command and metric denominators.

The vest is clearly distinct from the white shirt underneath. Shirt absence is
still a provisional sampled expectation: small distant people and unsampled
instants are not an exhaustive absence proof. No held-out test clips exist yet;
the six desk scenarios in dataset.json are missing footage. These results do not
establish general accuracy or complete milestone 1.


## Milestone 2 mechanisms - 2026-10-31 (no new live accuracy claims)

Code-level verification only; no new footage was indexed and no provider calls
were made for this section. The backend suite passes 85 tests locally (one
asyncio startup test is deselected in the current sandbox because Windows
asyncio loop creation is blocked there; the same hang reproduces on the
pre-milestone tree). New tests cover: selected clips never mixing (including
per-clip snapshot keys), unknown-clip searches checking zero frames,
first-seen/last-seen routing, budget exhaustion returning UNSURE with
`search.complete=false` instead of implying absence, last-seen stopping after
the newest positive batch, stored-sighting reuse spending zero new model
calls on a repeat query, last-seen refinement narrowing 2.0s -> 3.0s inside a
2.0-4.0s gap with the refined frame stored as evidence, attribute checks for
non-person bases, partial indexing (one failed frame) followed by a safe
retry that reuses the stored frame and reaches ready, and pan footage
producing no scene-change samples.

Latency/call comparison against the calibration baseline above is not yet
possible: the baseline numbers predate the `search` report (frames checked /
model calls were not recorded), and held-out temporal/attribute cases still
await milestone-1 footage and independent human labels. The vest/shirt
numbers above remain the only live accuracy evidence; a last-seen answer is
still a latest verified sampled sighting, not an exact exit time, and
`last_seen_interval` now states the checked bounds explicitly.
