"""Query-time retrieval and visual verification over indexed frames.

Milestone 2 behaviour:
- Queries may name one clip; a selected clip is never mixed with others.
- Verification runs recent-first in bounded batches under a per-query
  frame-check budget. When the budget stops a search early the response
  says so (``search.complete`` is false) instead of implying full coverage.
- Stored sightings and cached provider calls are reused as evidence before
  new model calls are spent.
- Last-seen searches stop at the first (newest-first) verified batch and
  may refine the timestamp inside the gap to the next checked negative
  observation. The result remains a sampled sighting, never an exact
  disappearance time; ``last_seen_interval`` carries the honest bounds.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path

from core.budget import activate, deactivate, install_counter, restore_counter
from core.contracts import QueryIntentModel, QueryResponse, SearchReport, TrailItem
from core.intent import parse_intent
from core.providers import get_model_client
from core.settings import get_settings
from core.masks import mask_overlay
from core.tracking import build_track
from core.verification import Detection, verify_frame
from core.files import atomic_write
from database import get_clip, get_db_path, init_db


@dataclass(frozen=True)
class IndexedFrame:
    id: str
    clip_id: str
    timestamp: float
    frame_path: str
    crop_path: str
    diff_bbox: list[float]
    caption: str
    objects: list[str]


@dataclass
class _SearchState:
    clip_id: str | None = None
    scope: str = ""
    frames_considered: int = 0
    frames_checked: int = 0
    checks_used: int = 0
    budget_exhausted: bool = False
    complete: bool = True
    evidence_reused: int = 0
    refined: bool = False
    counter: object = None
    model_calls: int = 0
    cached_calls_reused: int = 0

    @property
    def budget(self) -> int:
        return get_settings().query_max_frame_checks

    @property
    def budget_left(self) -> int:
        return max(0, self.budget - self.checks_used)

    def report(self) -> SearchReport:
        return SearchReport(
            clip_id=self.clip_id, scope=self.scope,
            frames_considered=self.frames_considered,
            frames_checked=self.frames_checked,
            frame_check_budget=self.budget,
            budget_exhausted=self.budget_exhausted, complete=self.complete,
            model_calls=self.model_calls, cached_calls_reused=self.cached_calls_reused,
            evidence_reused=self.evidence_reused, refined=self.refined)


def _row_to_frame(row: sqlite3.Row) -> IndexedFrame:
    return IndexedFrame(
        id=row["id"],
        clip_id=row["clip_id"],
        timestamp=row["ts"],
        frame_path=row["frame_path"],
        crop_path=row["crop_path"],
        diff_bbox=json.loads(row["diff_bbox"]),
        caption=row["caption"],
        objects=json.loads(row["objects_json"]),
    )


def _dedupe_frames(frames: list[IndexedFrame]) -> list[IndexedFrame]:
    seen: set[tuple[str, float]] = set()
    unique = []
    for frame in frames:
        key = (frame.clip_id, frame.timestamp)
        if key not in seen:
            seen.add(key)
            unique.append(frame)
    return unique


def retrieve_frames(normalized_query: str, limit: int | None = None,
                    clip_id: str | None = None) -> list[IndexedFrame]:
    """Recall mentions plus recent context, strictly inside the selected clip."""
    settings = get_settings()
    init_db(get_db_path())
    limit = limit or settings.recall_frame_count
    terms = [term for term in normalized_query.lower().split() if len(term) > 1]
    if not terms:
        return []
    clauses = " OR ".join("LOWER(objects_json) LIKE ? OR LOWER(caption) LIKE ?" for _ in terms)
    params: list = [value for term in terms for value in (f"%{term}%", f"%{term}%")]
    scope_clause = " AND clip_id = ?" if clip_id else ""
    if clip_id:
        params.append(clip_id)
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        order = "ts DESC, rowid DESC" if clip_id else "created_at DESC, ts DESC, rowid DESC"
        rows = conn.execute(
            f"SELECT * FROM frames WHERE ({clauses}){scope_clause} ORDER BY {order} LIMIT ?",
            (*params, limit)).fetchall()
        if not rows:
            fallback = "SELECT * FROM frames WHERE clip_id = ? ORDER BY ts DESC, rowid DESC LIMIT ?" if clip_id \
                else "SELECT * FROM frames ORDER BY created_at DESC, ts DESC, rowid DESC LIMIT ?"
            rows = conn.execute(fallback, (clip_id, limit) if clip_id else (limit,)).fetchall()
        else:
            context_clip = clip_id or rows[0]["clip_id"]
            context = conn.execute("SELECT * FROM frames WHERE clip_id=? ORDER BY ts DESC, rowid DESC LIMIT ?",
                                   (context_clip, limit)).fetchall()
            combined, seen = [], set()
            for pair in zip_longest(rows, context):
                for row in pair:
                    if row is not None and row["id"] not in seen:
                        combined.append(row)
                        seen.add(row["id"])
            rows = combined[:limit]
    finally:
        conn.close()
    return _dedupe_frames([_row_to_frame(row) for row in rows])


def _stored_detection(frame: IndexedFrame, label: str) -> Detection | None:
    """Reuse a previously verified sighting instead of spending a model call."""
    conn = sqlite3.connect(get_db_path())
    try:
        row = conn.execute(
            "SELECT bbox, mask_path, score FROM sightings WHERE frame_id=? AND query_label=? "
            "ORDER BY created_at DESC LIMIT 1", (frame.id, label)).fetchone()
    finally:
        conn.close()
    if not row or row[2] is None or row[2] < get_settings().sam_score_high:
        return None
    detection = Detection(score=row[2], bbox=json.loads(row[0]), mask=row[1])
    # Tracking associations use masked colour appearance; rebuild it from the
    # stored frame/box so a reused sighting is as strong as a fresh one.
    try:
        import cv2
        from core.verification import _appearance
        image = cv2.imread(frame.frame_path) if Path(frame.frame_path).is_file() else None
        detection.appearance = _appearance(image, detection)
    except Exception:
        detection.appearance = None
    return detection


def _verify_in_worker(state: _SearchState, frame: IndexedFrame, target: str) -> list[Detection]:
    token = activate(state.counter) if state.counter is not None else None
    try:
        return verify_frame(frame, target)
    finally:
        if token is not None:
            deactivate(token)


def _verify_batched(frames: list[IndexedFrame], target: str,
                    state: _SearchState) -> list[tuple[IndexedFrame, list[Detection]]]:
    """Verify recent-first in parallel batches until frames or budget run out.

    Stored sightings are reused without consuming the frame-check budget.
    Sets ``budget_exhausted``/``complete`` when unchecked frames remain.
    """
    settings = get_settings()
    results: list[tuple[IndexedFrame, list[Detection]]] = []
    pending: list[IndexedFrame] = []
    for frame in frames:
        stored = _stored_detection(frame, target)
        if stored is not None:
            state.frames_checked += 1
            state.evidence_reused += 1
            results.append((frame, [stored]))
        else:
            pending.append(frame)
    batch_size = max(1, settings.parallel_candidate_count)
    index = 0
    while index < len(pending):
        if state.budget_left <= 0:
            state.budget_exhausted = True
            state.complete = False
            break
        batch = pending[index:index + min(batch_size, state.budget_left)]
        index += len(batch)
        state.checks_used += len(batch)
        state.frames_checked += len(batch)
        with ThreadPoolExecutor(max_workers=min(len(batch), batch_size)) as executor:
            verified = list(executor.map(lambda frame: _verify_in_worker(state, frame, target), batch))
        results.extend(zip(batch, verified))
        # Re-sort so callers always see strict recent/oldest-first frame order.
        results.sort(key=lambda pair: pair[0].timestamp)
    if index < len(pending):
        state.budget_exhausted = True
        state.complete = False
    return results


def _trail_item(frame: IndexedFrame, hit: Detection, track_id: str | None = None) -> TrailItem:
    return TrailItem(frame_id=frame.id, ts=frame.timestamp, bbox=hit.bbox, score=hit.score,
                     mask_overlay=mask_overlay(hit.mask, hit.bbox), track_id=track_id, recovered=hit.recovered)


def query_memory(query: str, clip_id: str | None = None) -> QueryResponse:
    """Replay explicit offline snapshots; otherwise save successful responses.

    Snapshot keys include the selected clip so identical questions against
    different clips can never replay each other's evidence.
    """
    settings = get_settings()
    key = hashlib.sha256(f"{clip_id or ''}\n{query.strip().lower()}".encode()).hexdigest()
    path = settings.data_dir / "snapshots" / f"{key}.json"
    if settings.offline_snapshots:
        if not path.is_file():
            return QueryResponse(state="UNSURE", answer="No recorded offline result for this query.", query=query)
        return QueryResponse.model_validate_json(path.read_text(encoding="utf-8"))
    result = _query_memory(query, clip_id)
    atomic_write(path, result.model_dump_json())
    return result


def _intent_model(intent) -> QueryIntentModel:
    return QueryIntentModel(kind=intent.kind, target=intent.target,
                            base_object=intent.base_object, attribute=intent.attribute)


def _query_memory(query: str, clip_id: str | None = None) -> QueryResponse:
    original_query = query.strip()
    if not original_query:
        return QueryResponse(state="UNSURE", answer="Please name the item you are looking for.", query=query)

    counter, token = install_counter()
    try:
        client = get_model_client()
        normalized = client.normalize_query(original_query)
        intent = parse_intent(original_query, normalized)
        state = _SearchState(clip_id=clip_id)
        state.counter = counter
        if clip_id and not _clip_has_frames(clip_id):
            state.scope = f"Selected clip '{clip_id}' only"
            state.complete = False
            return QueryResponse(
                state="UNSURE", query=original_query, clip_id=clip_id, intent=_intent_model(intent),
                search=_finish(state, counter),
                answer=f"Clip '{clip_id}' has no indexed observations. Index it first; "
                       "no other clip was searched.")
        if intent.kind in {"last_seen", "first_seen"}:
            result = _temporal_search(original_query, intent, clip_id, state)
        else:
            result = _locate(original_query, intent, clip_id, state)
        result.search = _finish(state, counter)
        return result
    finally:
        restore_counter(token)


def _finish(state: _SearchState, counter) -> SearchReport:
    state.model_calls = counter.count
    state.cached_calls_reused = counter.cache_reused
    return state.report()


def _clip_has_frames(clip_id: str) -> bool:
    init_db(get_db_path())
    with sqlite3.connect(get_db_path()) as conn:
        return conn.execute("SELECT 1 FROM frames WHERE clip_id=? LIMIT 1", (clip_id,)).fetchone() is not None


def _clip_frames(clip_id: str) -> list[IndexedFrame]:
    init_db(get_db_path())
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM frames WHERE clip_id=? ORDER BY ts DESC, rowid DESC",
                            (clip_id,)).fetchall()
    return _dedupe_frames([_row_to_frame(row) for row in rows])


def _newest_clip_id() -> str | None:
    init_db(get_db_path())
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute("SELECT clip_id FROM frames ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
    return row[0] if row else None


def _locate(query: str, intent, clip_id: str | None, state: _SearchState) -> QueryResponse:
    normalized = intent.target
    candidates = retrieve_frames(normalized, clip_id=clip_id)
    state.frames_considered = len(candidates)
    state.scope = (f"Selected clip '{clip_id}' only" if clip_id else
                   "All indexed clips searched; evidence is reported from the newest matching clip")
    if not candidates:
        return QueryResponse(state="UNSURE", intent=_intent_model(intent),
                             answer=f"I could not find an indexed frame mentioning {normalized}.",
                             query=query, clip_id=clip_id)

    settings = get_settings()
    verified = _verify_batched(candidates, intent.verification_phrase, state)
    # Newest clip with a confident hit wins; clips are never mixed in one trail.
    verified.sort(key=lambda pair: (pair[0].timestamp), reverse=True)

    high_confidence = [(frame, [hit for hit in hits if hit.score >= settings.sam_score_high])
                       for frame, hits in verified if any(hit.score >= settings.sam_score_high for hit in hits)]
    if not high_confidence:
        possible = [(frame, hits[0]) for frame, hits in verified if hits and hits[0].score >= settings.sam_score_mid]
        possible.sort(key=lambda pair: pair[0].timestamp, reverse=True)
        if possible:
            frame, hit = possible[0]
            return QueryResponse(state="UNSURE", query=query, clip_id=frame.clip_id, intent=_intent_model(intent),
                                 answer=f"Possible match for {normalized}; I cannot verify it confidently.",
                                 frame_id=frame.id, frame_path=frame.frame_path, bbox=hit.bbox, mask=hit.mask,
                                 score=hit.score, recovered=hit.recovered, mask_overlay=mask_overlay(hit.mask, hit.bbox),
                                 trail=[_trail_item(frame, hit)])
        suffix = (" The frame-check budget was reached before every candidate could be checked."
                  if state.budget_exhausted else "")
        return QueryResponse(state="UNSURE", intent=_intent_model(intent), clip_id=clip_id,
                             answer=f"I found possible mentions of {normalized}, but could not verify it in the saved frames.{suffix}",
                             query=query)

    evidence_clip = clip_id or high_confidence[0][0].clip_id
    state.clip_id = evidence_clip
    observations = [(frame, [hit for hit in hits if hit.score >= settings.sam_score_high])
                    for frame, hits in verified if frame.clip_id == evidence_clip]
    latest_ts = max(frame.timestamp for frame, hits in observations if hits)
    observations = [(frame, hits) for frame, hits in observations if frame.timestamp <= latest_ts]
    track, movement = build_track(observations)
    latest_frame, latest_hit = track[-1]
    track_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{evidence_clip}:{normalized}:{latest_frame.id}"))
    trail = [_trail_item(frame, hit, track_id) for frame, hit in track]
    moved = movement.status == "moved"
    if intent.kind == "moved" and not moved:
        if movement.status == "stationary":
            answer = (f"{normalized.title()} was verified in {evidence_clip} and did not move beyond "
                      f"tolerance between associated sightings. Latest verified location is shown.")
            result_state = "FOUND_NOW"
        else:
            return QueryResponse(state="UNSURE", query=query, clip_id=evidence_clip, intent=_intent_model(intent),
                                 frame_id=latest_frame.id, frame_path=latest_frame.frame_path,
                                 bbox=latest_hit.bbox, mask=latest_hit.mask, score=latest_hit.score,
                                 recovered=latest_hit.recovered, movement=movement, track_id=track_id,
                                 mask_overlay=trail[-1].mask_overlay, trail=trail,
                                 answer=f"{normalized.title()} was found, but whether it moved is uncertain: {movement.reason}")
    else:
        result_state = "MOVED" if moved else "FOUND_NOW"
        if moved:
            answer = f"{normalized.title()} appears to have moved between associated sightings after accounting for camera motion; the latest verified location is shown."
        else:
            answer = f"{normalized.title()} was found in the latest matching indexed frame."
    client = get_model_client()
    spatial = client.describe_spatial(latest_frame.frame_path, normalized)
    answer += f" On {spatial.surface}, {spatial.anchor}. Visibility: {spatial.visibility}."
    if movement.status == "unknown" and intent.kind != "moved":
        answer += f" Movement is uncertain: {movement.reason}"
    if not state.complete:
        answer += " The frame-check budget was reached, so older sightings may be unchecked; the trail is partial."
    if any(frame.timestamp > latest_ts for frame, _ in verified if frame.clip_id == evidence_clip):
        answer += " It was not confidently verified in later searched observations; this does not establish absence."
    _store_sightings(track, normalized, track_id, movement, spatial, latest_frame)
    return QueryResponse(
        state=result_state, bbox=latest_hit.bbox, mask=latest_hit.mask,
        mask_overlay=trail[-1].mask_overlay, movement=movement, track_id=track_id,
        score=latest_hit.score, recovered=latest_hit.recovered, trail=trail,
        answer=answer, query=query, clip_id=evidence_clip, intent=_intent_model(intent),
        frame_path=latest_frame.frame_path, frame_id=latest_frame.id)


def _store_sightings(track, normalized, track_id, movement, spatial, latest_frame) -> None:
    conn = sqlite3.connect(get_db_path())
    try:
        conn.execute("BEGIN IMMEDIATE")
        for frame, hit in track:
            exists = conn.execute("SELECT id FROM sightings WHERE frame_id=? AND query_label=?",
                                  (frame.id, normalized)).fetchone()
            spatial_json = spatial.model_dump_json() if frame.id == latest_frame.id else "{}"
            if exists:
                conn.execute("UPDATE sightings SET bbox=?,mask_path=?,score=?,spatial_json=?,track_id=?,tracking_json=? WHERE id=?",
                             (json.dumps(hit.bbox), hit.mask, hit.score, spatial_json, track_id, movement.model_dump_json(), exists[0]))
            else:
                conn.execute("INSERT INTO sightings (id,frame_id,query_label,bbox,mask_path,score,spatial_json,track_id,tracking_json) VALUES (?,?,?,?,?,?,?,?,?)",
                             (str(uuid.uuid4()), frame.id, normalized, json.dumps(hit.bbox), hit.mask, hit.score, spatial_json,
                              track_id, movement.model_dump_json()))
        conn.commit()
    finally:
        conn.close()


def _temporal_search(query: str, intent, clip_id: str | None, state: _SearchState) -> QueryResponse:
    """Search one clip newest-first (last seen) or oldest-first (first seen)."""
    resolved = clip_id or _newest_clip_id()
    if resolved is None:
        return QueryResponse(state="UNSURE", answer="Index a clip before searching.", query=query,
                             intent=_intent_model(intent))
    state.clip_id = resolved
    state.scope = (f"Selected clip '{resolved}' only" if clip_id else
                   f"Newest indexed clip '{resolved}' only")
    frames = _clip_frames(resolved)
    if intent.kind == "first_seen":
        frames = list(reversed(frames))
    state.frames_considered = len(frames)
    if not frames:
        return QueryResponse(state="UNSURE", answer="Index a clip before searching.", query=query,
                             clip_id=resolved, intent=_intent_model(intent))

    settings = get_settings()
    batch_size = max(1, settings.parallel_candidate_count)
    found: tuple[IndexedFrame, Detection] | None = None
    checked_negative_bounds: list[float] = []
    index = 0
    while index < len(frames) and found is None:
        if state.budget_left <= 0:
            state.budget_exhausted = True
            state.complete = False
            break
        batch = frames[index:index + min(batch_size, state.budget_left)]
        index += len(batch)
        state.checks_used += len(batch)
        state.frames_checked += len(batch)
        with ThreadPoolExecutor(max_workers=min(len(batch), batch_size)) as executor:
            verified = list(executor.map(lambda frame: _verify_in_worker(state, frame, intent.verification_phrase), batch))
        for frame, detections in zip(batch, verified):
            hits = [hit for hit in detections if hit.score >= settings.sam_score_high]
            if hits:
                candidate = (frame, max(hits, key=lambda item: item.score))
                if found is None or (intent.kind == "last_seen" and frame.timestamp > found[0].timestamp) \
                        or (intent.kind == "first_seen" and frame.timestamp < found[0].timestamp):
                    found = candidate
            else:
                checked_negative_bounds.append(frame.timestamp)
    if found is None:
        if state.budget_exhausted:
            return QueryResponse(state="UNSURE", query=query, clip_id=resolved, intent=_intent_model(intent),
                                 answer=f"Could not verify {intent.target} before the frame-check budget "
                                        f"({state.budget} checks) was reached; {len(frames) - state.frames_checked} "
                                        "indexed observation(s) remain unchecked, so this is not evidence of absence.")
        return QueryResponse(state="UNSURE", query=query, clip_id=resolved, intent=_intent_model(intent),
                             answer=f"Could not verify {intent.target} in any indexed observation of {resolved}.")

    frame, hit = found
    boundary: float | None = None
    if intent.kind == "last_seen":
        later_negatives = [ts for ts in checked_negative_bounds if ts > frame.timestamp]
        boundary = min(later_negatives) if later_negatives else None
        if boundary is not None and state.budget_left > 0:
            refined = _refine_boundary(resolved, intent, frame, hit, boundary, state)
            if refined is not None:
                frame, hit, boundary = refined
                state.refined = True
    else:
        earlier_negatives = [ts for ts in checked_negative_bounds if ts < frame.timestamp]
        boundary = max(earlier_negatives) if earlier_negatives else None

    interval = None
    if boundary is not None:
        interval = sorted([frame.timestamp, boundary])
    if intent.kind == "last_seen":
        answer = (f"Latest verified sampled sighting of {intent.target}: {frame.timestamp:.2f}s into {resolved}. "
                  "Frames between indexed observations remain unverified; this is not an exact exit time.")
        if state.refined:
            answer += (f" Finer checks narrowed the last sighting; the object was last verified at "
                       f"{frame.timestamp:.2f}s and not verified at {boundary:.2f}s.")
    else:
        answer = (f"Earliest verified sampled sighting of {intent.target}: {frame.timestamp:.2f}s into {resolved}. "
                  "Frames between indexed observations remain unverified; this is not an exact entry time.")
    return QueryResponse(state="FOUND_NOW", query=query, clip_id=resolved, intent=_intent_model(intent),
                         last_seen_seconds=frame.timestamp, last_seen_interval=interval,
                         frame_id=frame.id, frame_path=frame.frame_path,
                         bbox=hit.bbox, score=hit.score, recovered=hit.recovered,
                         mask_overlay=mask_overlay(hit.mask, hit.bbox), trail=[_trail_item(frame, hit)],
                         answer=answer)


def _refine_boundary(clip_id: str, intent, frame: IndexedFrame, hit: Detection,
                     next_negative: float, state: _SearchState):
    """Binary-search the gap after the last positive with finer extracted frames.

    Only runs when the clip's source video is still on disk. Refined frames are
    stored as first-class indexed observations so their evidence can be
    served and reused. Returns (frame, hit, refined_next_negative) or None.
    """
    settings = get_settings()
    clip = get_clip(clip_id)
    source = clip and clip.get("source_path")
    if not source or not Path(source).is_file() or settings.query_refinement_max_checks <= 0:
        return None
    checks = min(settings.query_refinement_max_checks, state.budget_left)
    if checks <= 0:
        return None
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        return None
    lo, hi = frame.timestamp, next_negative
    best_frame, best_hit = frame, hit
    improved = False
    try:
        for _ in range(checks):
            if hi - lo <= 0.05:
                break
            mid = (lo + hi) / 2
            cap.set(cv2.CAP_PROP_POS_MSEC, mid * 1000)
            ok, image = cap.read()
            if not ok or image is None:
                break
            height, width = image.shape[:2]
            folder = settings.data_dir / "frames" / clip_id
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"frame_refined_{mid:.3f}.jpg"
            if not cv2.imwrite(str(path), image):
                break
            refined_frame = _insert_refined_frame(clip_id, mid, str(path), [0, 0, width, height], intent.target)
            state.checks_used += 1
            state.frames_checked += 1
            hits = [item for item in verify_frame(refined_frame, intent.verification_phrase)
                    if item.score >= settings.sam_score_high]
            if hits:
                lo = mid
                best_frame, best_hit = refined_frame, max(hits, key=lambda item: item.score)
                improved = True
            else:
                hi = mid
    finally:
        cap.release()
    if not improved:
        return None
    return best_frame, best_hit, hi


def _insert_refined_frame(clip_id: str, timestamp: float, frame_path: str,
                          diff_bbox: list[int], target: str) -> IndexedFrame:
    init_db(get_db_path())
    frame_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"refined:{clip_id}:{timestamp:.3f}:{target}"))
    conn = sqlite3.connect(get_db_path())
    try:
        conn.execute(
            "INSERT OR IGNORE INTO frames (id, clip_id, ts, frame_path, crop_path, diff_bbox, caption, objects_json, sampling_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'refinement')",
            (frame_id, clip_id, timestamp, frame_path, frame_path, json.dumps(diff_bbox),
             "Refined temporal-search observation (extracted between indexed samples; not VLM-captioned).",
             json.dumps([target])))
        conn.commit()
    finally:
        conn.close()
    return IndexedFrame(id=frame_id, clip_id=clip_id, timestamp=timestamp, frame_path=frame_path,
                        crop_path=frame_path, diff_bbox=diff_bbox, caption="", objects=[target])
