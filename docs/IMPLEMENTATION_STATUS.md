# Improvements — 2026-10-30

The core index → query → evidence workflow now includes these implemented changes:

- Pixel-accurate one-bit/lossless SAM mask decoding through the official Python
  codec, with transparent PNG overlays in full-frame coordinates. Each trail item
  carries its own mask. Legacy or invalid tokens retain box-only evidence.
- Query-local association using masked appearance, relative size, and geometry.
  ORB/RANSAC background alignment compensates for camera translation, rotation,
  and zoom. Movement has absolute and relative tolerances, including cumulative
  drift and move-then-return cases. Ambiguity, missing observations, long gaps,
  and unreliable alignment produce unknown movement.
- Bounded contextual zoom, full-frame recovery, and overlapping tile reruns for
  weak/tiny objects, with source-coordinate mapping and duplicate suppression.
- Scripted found/moved/uncertain demos with synthetic stills, reference clips,
  actual masks, persisted sightings, and offline snapshots.
- Per-frame evidence selection, mask/box toggles, zoom, model scores, recovery
  labels, image errors, and explicit historical/uncertain wording.
- Additive sighting metadata migration, versioned provider caches, atomic cache/
  snapshot/recovery-file publishing, bounded request lengths, protected clip
  names, and blocking work moved into FastAPI's worker pool. The unused Tailwind
  starter loader was removed after it crashed production compilation; plain CSS
  builds successfully.

Validation uses synthetic images and provider test doubles. The demo exercises the
actual query, mask, tracking, storage, and HTTP/frontend paths, but its detector is
scripted. Earlier live smoke tests establish the provider transport, not the accuracy
of these new recovery/tracking heuristics.

Verification for this revision:

- 54 backend tests passed, including the three demo states and snapshot replay.
- TypeScript, ESLint, and the production Next.js build passed.
- Production browser checks passed for video indexing, duplicate-clip rejection,
  found/moved/uncertain results, per-sighting mask coordinates, mask toggles, zoom,
  and uncertain-match wording. The layout was inspected at desktop and narrow widths.

Still incomplete before calling these stages production-ready:

- Real desk-video calibration, labeled accuracy evaluation, and live high-resolution
  recovery validation. Color histograms cannot reliably distinguish all lookalikes.
- Dense temporal/video tracking, identity across occlusion or re-entry, general
  perspective/parallax compensation, and broader sampling coverage. The current
  sampler can still produce just one observation for continuous-motion footage.
- Resource budgets across simultaneous requests, authentication, background jobs,
  cancellation, cleanup/retention, and public-hosting hardening.

The original locally ignored roadmap is retained; partial stages should not be
marked complete merely because these implementations and synthetic demos pass.
