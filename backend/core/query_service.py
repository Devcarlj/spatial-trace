"""Query-time retrieval and visual verification over indexed frames."""

from __future__ import annotations

import json
import sqlite3
import uuid
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import zip_longest

from core.contracts import QueryResponse, TrailItem
from core.providers import get_model_client
from core.settings import get_settings
from core.masks import mask_overlay
from core.tracking import build_track
from core.verification import Detection, verify_frame
from core.files import atomic_write
from database import get_db_path, init_db


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


def retrieve_frames(normalized_query: str, limit: int | None = None) -> list[IndexedFrame]:
    """Recall mentions plus recent context to check gaps and uncaptioned objects."""
    settings = get_settings()
    init_db(get_db_path())
    limit = limit or settings.recall_frame_count
    terms = [term for term in normalized_query.lower().split() if len(term) > 1]
    if not terms:
        return []
    clauses = " OR ".join("LOWER(objects_json) LIKE ? OR LOWER(caption) LIKE ?" for _ in terms)
    params = [value for term in terms for value in (f"%{term}%", f"%{term}%")] + [limit]
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT * FROM frames WHERE {clauses} ORDER BY created_at DESC, ts DESC, rowid DESC LIMIT ?", params
        ).fetchall()
        if not rows:
            rows = conn.execute("SELECT * FROM frames ORDER BY created_at DESC, ts DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
        else:
            context = conn.execute("SELECT * FROM frames WHERE clip_id=? ORDER BY ts DESC, rowid DESC LIMIT ?",
                                   (rows[0]["clip_id"], limit)).fetchall()
            combined, seen = [], set()
            for pair in zip_longest(rows, context):
                for row in pair:
                    if row is not None and row["id"] not in seen:
                        combined.append(row)
                        seen.add(row["id"])
            rows = combined[:limit]
    finally:
        conn.close()
    return [_row_to_frame(row) for row in rows]


def _trail_item(frame: IndexedFrame, hit: Detection, track_id: str | None = None) -> TrailItem:
    return TrailItem(frame_id=frame.id, ts=frame.timestamp, bbox=hit.bbox, score=hit.score,
                     mask_overlay=mask_overlay(hit.mask, hit.bbox), track_id=track_id, recovered=hit.recovered)


def query_memory(query: str) -> QueryResponse:
    """Replay explicit offline snapshots; otherwise save successful responses."""
    settings = get_settings()
    key = hashlib.sha256(query.strip().lower().encode()).hexdigest()
    path = settings.data_dir / "snapshots" / f"{key}.json"
    if settings.offline_snapshots:
        if not path.is_file():
            return QueryResponse(state="UNSURE", answer="No recorded offline result for this query.", query=query)
        return QueryResponse.model_validate_json(path.read_text(encoding="utf-8"))
    result = _query_memory(query)
    atomic_write(path, result.model_dump_json())
    return result


def _query_memory(query: str) -> QueryResponse:
    """Resolve a natural-language item query against the indexed video history."""
    original_query = query.strip()
    if not original_query:
        return QueryResponse(state="UNSURE", answer="Please name the item you are looking for.", query=query)

    client = get_model_client()
    normalized = client.normalize_query(original_query)
    if re.search(r"\b(last time|last seen|latest appearance)\b", original_query, re.I):
        return _last_seen(original_query, normalized)
    candidates = retrieve_frames(normalized)
    if not candidates:
        return QueryResponse(
            state="UNSURE",
            answer=f"I could not find an indexed frame mentioning {normalized}.",
            query=original_query,
        )

    settings = get_settings()
    with ThreadPoolExecutor(max_workers=min(len(candidates), settings.parallel_candidate_count)) as executor:
        verified = list(executor.map(lambda frame: (frame, verify_frame(frame, normalized)), candidates))

    high_confidence = [(frame, [hit for hit in hits if hit.score >= settings.sam_score_high])
                       for frame, hits in verified if any(hit.score >= settings.sam_score_high for hit in hits)]
    if not high_confidence:
        possible = [(frame, hits[0]) for frame, hits in verified if hits and hits[0].score >= settings.sam_score_mid]
        if possible:
            frame, hit = possible[0]
            return QueryResponse(state="UNSURE", query=original_query,
                                 answer=f"Possible match for {normalized}; I cannot verify it confidently.",
                                 frame_id=frame.id, frame_path=frame.frame_path, bbox=hit.bbox, mask=hit.mask,
                                 score=hit.score, recovered=hit.recovered, mask_overlay=mask_overlay(hit.mask, hit.bbox),
                                 trail=[_trail_item(frame, hit)])
        return QueryResponse(
            state="UNSURE",
            answer=f"I found possible mentions of {normalized}, but could not verify it in the saved frames.",
            query=original_query,
        )

    # Clip-relative seconds cannot establish ordering between unrelated clips.
    newest_clip = high_confidence[0][0].clip_id
    observations = [(frame, [hit for hit in hits if hit.score >= settings.sam_score_high])
                    for frame, hits in verified if frame.clip_id == newest_clip]
    # A later non-detection does not invalidate a historical sighting, but we do
    # not bridge an unverified observation when associating a track.
    latest_ts = max(frame.timestamp for frame, hits in observations if hits)
    observations = [(frame, hits) for frame, hits in observations if frame.timestamp <= latest_ts]
    track, movement = build_track(observations)
    latest_frame, latest_hit = track[-1]
    track_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{newest_clip}:{normalized}:{latest_frame.id}"))
    trail = [_trail_item(frame, hit, track_id) for frame, hit in track]
    moved = movement.status == "moved"
    state = "MOVED" if moved else "FOUND_NOW"
    if moved:
        answer = f"{normalized.title()} appears to have moved between associated sightings after accounting for camera motion; the latest verified location is shown."
    else:
        answer = f"{normalized.title()} was found in the latest matching indexed frame."
    spatial = client.describe_spatial(latest_frame.frame_path, normalized)
    answer += f" On {spatial.surface}, {spatial.anchor}. Visibility: {spatial.visibility}."
    if movement.status == "unknown":
        answer += f" Movement is uncertain: {movement.reason}"
    if any(frame.timestamp > latest_ts for frame, _ in verified if frame.clip_id == newest_clip):
        answer += " It was not confidently verified in later searched observations; this does not establish absence."
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
    return QueryResponse(
        state=state,
        bbox=latest_hit.bbox,
        mask=latest_hit.mask,
        mask_overlay=trail[-1].mask_overlay,
        movement=movement,
        track_id=track_id,
        score=latest_hit.score,
        recovered=latest_hit.recovered,
        trail=trail,
        answer=answer,
        query=original_query,
        frame_path=latest_frame.frame_path,
        frame_id=latest_frame.id,
    )


def _last_seen(query: str, normalized: str) -> QueryResponse:
    """Search the entire newest clip in reverse time, without caption filtering."""
    init_db(get_db_path())
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        newest = conn.execute("SELECT clip_id FROM frames ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
        if newest is None:
            return QueryResponse(state="UNSURE", answer="Index a clip before searching.", query=query)
        rows = conn.execute("SELECT * FROM frames WHERE clip_id=? ORDER BY ts DESC, rowid DESC", (newest[0],)).fetchall()
    seen = set()
    frames = []
    for row in rows:
        frame = _row_to_frame(row)
        if frame.timestamp in seen:
            continue
        seen.add(frame.timestamp)
        frames.append(frame)
    settings = get_settings()
    with ThreadPoolExecutor(max_workers=settings.parallel_candidate_count) as executor:
        verified = list(executor.map(lambda frame: verify_frame(frame, normalized), frames))
    for frame, detections in zip(frames, verified):
        hits = [hit for hit in detections if hit.score >= settings.sam_score_high]
        if hits:
            hit = max(hits, key=lambda item: item.score)
            return QueryResponse(state="FOUND_NOW", query=query, clip_id=frame.clip_id,
                                 last_seen_seconds=frame.timestamp, frame_id=frame.id, frame_path=frame.frame_path,
                                 bbox=hit.bbox, score=hit.score, recovered=hit.recovered,
                                 mask_overlay=mask_overlay(hit.mask, hit.bbox), trail=[_trail_item(frame, hit)],
                                 answer=f"Latest verified sampled sighting of {normalized}: {frame.timestamp:.2f}s into {frame.clip_id}. "
                                        "Frames between indexed observations remain unverified; this is not an exact exit time.")
    return QueryResponse(state="UNSURE", query=query, clip_id=newest[0],
                         answer=f"Could not verify {normalized} in any indexed observation of the newest clip.")
