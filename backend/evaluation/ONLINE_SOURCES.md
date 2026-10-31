# Online sources for the six Milestone 1 scenarios (2026-10-31)

Yes, online video can substitute for *some* desk-capture footage. All six clips
below are Mixkit Free License assets (https://mixkit.co/license/#videoFree),
downloaded 2026-10-31 with `fetch_online_sources.py` into the ignored folder
`backend/data/evaluation/online-sources/final/` (keep footage outside git).
Each manifest records its asset URL, SHA-256, FPS, frame count, and duration.

| Scenario | Split | Clip (ignored local file) | Duration | What it actually tests |
|---|---|---|---|---|
| static_camera | calibration | online_static_camera.mp4 | 16.2s | Static camera, stationary laptop, absent coffee-mug control |
| handheld_pan | held_out | online_handheld_pan.mp4 | 6.3s | Smooth pan over world-stationary desk items (not handheld shake; shorter than guide) |
| lighting_change | calibration | online_lighting_change.mp4 | 13.0s | Fixed bulb, dark -> bright -> dark |
| occlusion | calibration | online_occlusion.mp4 | 18.5s | Calculator covered by falling coins, then revealed in place (no hide-then-move) |
| similar_items | calibration | online_similar_items.mp4 | 12.1s | Many similar coins; single-coin identity honestly `unknown` |
| tiny_objects | held_out | online_tiny_objects.mp4 | 20.0s trimmed | One small spinning coin (no multi-distance / between-keyframe case) |

Manifests: `online_static_camera.json`, `online_handheld_pan.json`,
`online_lighting_change.json`, `online_occlusion.json`,
`online_similar_items.json`, `online_tiny_objects.json`.

## Honest limits - Milestone 1 is NOT complete

- Labels are agent visual review of full-resolution frames. The capture guide
  requires **independent human review** before a scenario is marked complete.
- Stock clips do not reproduce the guide's scripted actions (move-then-remove,
  hide-then-move, two similar pens with one moved, tiny object at several
  distances). Scenario fidelity is partial and is documented per manifest.
- No mask labels were created (mask IoU stays unmeasured), and no clip has been
  indexed yet: sample timestamps must be checked against the sampler's indexed
  timestamps after indexing, and unindexed labels report as missing coverage.
- Next steps: human-review each manifest, index the matching clip last before
  running `evaluate.py <manifest> --samples`, then publish the baseline report.
