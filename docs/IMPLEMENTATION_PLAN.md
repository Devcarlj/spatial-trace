# SpatialTrace roadmap

Updated: 2026-10-30. This is the authoritative plan, superseding the locally
ignored `.agents/docs/IMPLEMENTATION_PLAN.md`. See [current status](IMPLEMENTATION_STATUS.md)
for capabilities and [evaluation results](../backend/evaluation/RESULTS.md) for evidence.

## Product goal and current position

Index recorded footage, answer where an object was last seen or whether it moved,
and show the supporting timestamp, frame, box/mask, and uncertainty. The current
delivery target is a dependable local application.

The local prototype works end to end. Coverage sampling, masks, recovery,
conservative movement association, and initial person/clothing last-seen queries
are implemented. Broad real-video accuracy, acceptable latency, and continued-use
controls remain incomplete. The latest recorded backend run passed 62 tests;
two initial live clothing checks passed with limited manual sample labels.

## Milestone 1 — establish the real-video baseline (next)

Complete this before tuning tracking thresholds or adding recovery passes.

- Finish annotating the existing coastal recording across its duration: visible
  intervals, sampled boxes, garment distinctions, and final visibility. Review
  the provisional blue-shirt negative expectation.
- Assemble at least six short local clips covering static camera, handheld pan,
  lighting changes, occlusion, similar items, and tiny objects. Include present,
  absent, ambiguous, stationary, and moved cases. Track source identifiers in
  manifests; keep private footage outside git.
- Extend evaluation with detection precision/recall, box overlap, mask overlap
  where labeled, false movement claims, last-seen error, uncertainty outcomes,
  sampling coverage, and latency. Report missing labels explicitly.
- Record configuration, models, source versions, cache state, and per-case results.
  Split calibration cases from held-out clips before tuning.

Completion: all six scenarios have reviewed labels and reproducible cases; one
documented command produces the baseline report; positive/negative controls catch
wrong clips, timestamps, objects, and movement. Publish measurements and propose
accuracy/latency targets for review. Product-wide targets are not yet agreed.

## Milestone 2 — accurate, affordable temporal search

- Explicit clip selection across API, UI, and evaluator; consistent scope wording.
- Structured temporal intent and attributes beyond current person phrase patterns.
- Per-request model-call budgets, recent-first batches, and evidence reuse.
  Report uncertainty when budgets prevent a complete search.
- Calibrate visual-change sampling against pans/redundancy; refine time near the
  last positive observation where finer timing is needed.
- Explicit partial/failed indexing states and safe retry behavior.

Completion: selected clips cannot mix; held-out temporal/attribute cases pass
agreed criteria; compare latency and calls against the baseline with cache state
stated. Report accuracy tradeoffs and distinguish last sampled sightings from
exact disappearance times.

## Milestone 3 — responsive jobs and a clip library

- Background index/query jobs with durable states, progress, cancellation,
  visible failures, and bounded concurrency/provider requests.
- Video-duration, file-size, frame-count, storage, and model-call limits.
- Local library with clip selection and ready/partial/failed states.

Completion: exercise successful jobs, cancellation, provider failure, restart,
limit rejection, and concurrent submissions. UI remains responsive; canceled work
stops scheduling new model calls; status identifies incomplete evidence.

## Milestone 4 — occlusion and re-entry tracking

- Visible/lost/re-acquired states and confidence-based association.
- Evaluate lookalikes, disappearance, re-entry, camera motion, and long gaps.
- Require identity evidence before joining sightings or claiming movement.

Completion: held-out cases report association errors and false movement rates;
ambiguous re-entry stays uncertain; persistent-track behavior is documented.

## Milestone 5 — review and correction workflow

- Previous/latest side-by-side movement evidence.
- Per-frame recovery reasons and attribute outcomes; distinguish detector scores
  from attribute confirmation.
- Bad-result flags and export of corrections into calibration.
- Clear clip scope, sampled coverage, and job progress.

Completion: reviewers can inspect both movement frames, understand acceptance,
flag errors, and recover corrections for evaluation. Verify desktop/narrow layouts
and failed image/job states.

## Milestone 6 — storage and release hardening

- Retention, clip deletion, storage accounting, abandoned-artifact cleanup, and
  evidence-reference integrity.
- Backup/restore, configuration, failure recovery, and supported-limit docs.
- Authentication, authorization, and deployment controls before public hosting;
  trusted loopback remains the current scope.

Completion: deletion preserves other clips, restored evidence resolves, storage
stays within limits, and the intended deployment passes documented access and
concurrency checks.

## Original six priorities and status

1. Real-video test set: started; milestone 1 completes the initial set.
2. Evaluation: partial; milestone 1 expands the temporal runner.
3. Coverage: implemented baseline; milestone 2 calibrates/refines it.
4. Occlusion/re-entry: partial safeguards; milestone 4 adds states.
5. Review UI: partial; milestone 5 completes the workflow.
6. Continued-use hardening: partial; milestones 3 and 6 deliver job/storage controls.

## Plan maintenance

Progress on 2026-10-30: the expanded evaluator, source review/contact-sheet tool,
dataset inventory, and capture guide are implemented. The coastal calibration
baseline has 5/5 frame checks and 2/2 HTTP queries passing; 69 backend tests pass.
Thirty source samples span the recording. All six desk scenarios still need
footage/review; mask and movement labels and held-out data are missing. Next:
collect those clips and labels, then run the baseline before threshold tuning.

“Implemented” means code exists; “validated” requires recorded evidence;
“complete” requires the milestone criteria. Update status/evidence when results
or scope change. Separate synthetic checks from live accuracy and cached timings
from cold-cache measurements. The next implementation action is milestone 1.
