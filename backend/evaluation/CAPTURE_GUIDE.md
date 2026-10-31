# Initial desk-video capture and labeling

Record six separate 15-30 second clips. Keep original files outside git; keep
derived frames/reports under ignored backend/data/evaluation. Use objects with
visible boundaries: mug, keys, pen, coin, USB drive. Avoid private screens.

1. Static camera: hold a view of two objects, move one, then remove it. Leave the
   other stationary throughout. Include a query for an object never present.
2. Handheld pan: pan across stationary items, then return. Camera movement must
   not become an object-movement claim.
3. Lighting: keep objects stationary while switching a lamp or casting a shadow.
4. Occlusion: hide an object for 2-3 seconds and reveal it in the same position;
   then hide and move it. Record when identity becomes unclear.
5. Similar items: two similar pens or mugs, move only one, and cross or occlude
   them. Do not assign an identity label when visual evidence is insufficient.
6. Tiny objects: coin/USB/key at several distances, briefly present and absent.
   Include a short appearance between the normal two-second keyframes.

Before tuning, assign whole source clips to calibration or held_out in manifests.
Use at least two held-out clips initially; broader claims need held-out examples
of each scenario. Do not mix adjacent frames of a source across splits.

Generate review frames with review_video.py (see README). Record source SHA-256,
duration, FPS, and reviewer. Inspect original-resolution frames near transitions.
Record sampled last visibility separately from exact exit boundaries. Require an
independent human review before marking a scenario complete in dataset.json.

Each sample needs timestamp, target, review_status="reviewed", and objects with
all visible target boxes in full-frame pixel xyxy coordinates. objects=[] means
reviewed absence of that target; omit unresolved samples rather than calling
them negative. Use mask_path for an optional full-frame binary PNG (white target,
black background), relative to the manifest directory. Hand-label masks; do not
use the detector's own output as ground truth. Match each mask to its object box.

Temporal query cases need query and expected_last_seen_seconds (null for absence).
Positive cases also need expected_bbox and tolerance_seconds. For ordinary
movement queries set kind="movement" and expected_movement to moved, stationary,
or unknown; these do not require temporal labels. Annotate world movement,
not apparent displacement from camera motion. Add stationary cases before
interpreting a false-movement rate.

Current last-seen queries use the newest indexed clip. Index the matching source
last before evaluating; wrong-clip results fail. Explicit clip selection belongs
to milestone 2. Record the returned indexed timestamps before writing sample
cases: an unindexed label is reported as missing coverage, not a detector miss.
