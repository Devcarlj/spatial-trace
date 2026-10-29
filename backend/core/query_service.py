"""Query-time retrieval and visual verification over indexed frames."""

from __future__ import annotations

import json
import sqlite3
import uuid
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from core.contracts import QueryResponse, TrailItem
from core.providers import get_model_client
from core.settings import get_settings
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
    """Return newest indexed frames whose caption or labels mention the query."""
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
            f"SELECT * FROM frames WHERE {clauses} ORDER BY created_at DESC, ts DESC LIMIT ?", params
        ).fetchall()
        if not rows:
            rows = conn.execute("SELECT * FROM frames ORDER BY created_at DESC, ts DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    return [_row_to_frame(row) for row in rows]


def _full_frame_box(frame: IndexedFrame, crop_box: list[float]) -> list[float]:
    crop_x, crop_y = frame.diff_bbox[:2]
    x1, y1, x2, y2 = crop_box
    return [x1 + crop_x, y1 + crop_y, x2 + crop_x, y2 + crop_y]


def _verify(frame: IndexedFrame, noun_phrase: str) -> tuple[IndexedFrame, float, list[float] | None, str | None]:
    response = get_model_client().sam_segment(frame.crop_path, noun_phrase)
    if not response.scores:
        return frame, 0.0, None, None
    position = max(range(len(response.scores)), key=response.scores.__getitem__)
    box = response.boxes[position] if position < len(response.boxes) else None
    mask = response.masks[position] if position < len(response.masks) else None
    return frame, response.scores[position], _full_frame_box(frame, box) if box else None, mask


def _has_moved(trail: list[TrailItem]) -> bool:
    if len(trail) < 2 or not trail[0].bbox or not trail[-1].bbox:
        return False
    first, last = trail[0].bbox, trail[-1].bbox
    return first[:2] != last[:2]


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(), encoding="utf-8")
    return result


def _query_memory(query: str) -> QueryResponse:
    """Resolve a natural-language item query against the indexed video history."""
    original_query = query.strip()
    if not original_query:
        return QueryResponse(state="UNSURE", answer="Please name the item you are looking for.", query=query)

    client = get_model_client()
    normalized = client.normalize_query(original_query)
    candidates = retrieve_frames(normalized)
    if not candidates:
        return QueryResponse(
            state="UNSURE",
            answer=f"I could not find an indexed frame mentioning {normalized}.",
            query=original_query,
        )

    settings = get_settings()
    candidates = candidates[: settings.parallel_candidate_count]
    with ThreadPoolExecutor(max_workers=len(candidates)) as executor:
        verified = list(executor.map(lambda frame: _verify(frame, normalized), candidates))

    high_confidence = [item for item in verified if item[1] >= settings.sam_score_high and item[2]]
    if not high_confidence:
        possible = [item for item in verified if item[1] >= settings.sam_score_mid and item[2]]
        if possible:
            frame, score, box, mask = possible[0]
            return QueryResponse(state="UNSURE", query=original_query,
                                 answer=f"Possible match for {normalized}; I cannot verify it confidently.",
                                 frame_id=frame.id, frame_path=frame.frame_path, bbox=box, mask=mask,
                                 trail=[TrailItem(frame_id=frame.id, ts=frame.timestamp, bbox=box, score=score)])
        return QueryResponse(
            state="UNSURE",
            answer=f"I found possible mentions of {normalized}, but could not verify it in the saved frames.",
            query=original_query,
        )

    # Clip-relative seconds cannot establish ordering between unrelated clips.
    newest_clip = high_confidence[0][0].clip_id
    high_confidence = [item for item in high_confidence if item[0].clip_id == newest_clip]
    high_confidence.sort(key=lambda item: item[0].timestamp)
    trail = [TrailItem(frame_id=frame.id, ts=frame.timestamp, bbox=box, score=score) for frame, score, box, _ in high_confidence[-3:]]
    latest_frame, latest_score, latest_box, latest_mask = high_confidence[-1]
    moved = _has_moved(trail)
    state = "MOVED" if moved else "FOUND_NOW"
    if moved:
        answer = f"{normalized.title()} appears to have moved; its latest indexed location is in the most recent matching frame."
    else:
        answer = f"{normalized.title()} was found in the latest matching indexed frame."
    spatial = client.describe_spatial(latest_frame.frame_path, normalized)
    answer += f" On {spatial.surface}, {spatial.anchor}. Visibility: {spatial.visibility}."
    conn = sqlite3.connect(get_db_path())
    try:
        for frame, score, box, mask in high_confidence[-3:]:
            exists = conn.execute("SELECT id FROM sightings WHERE frame_id=? AND query_label=?",
                                  (frame.id, normalized)).fetchone()
            if not exists:
                conn.execute("INSERT INTO sightings (id,frame_id,query_label,bbox,mask_path,score,spatial_json) VALUES (?,?,?,?,?,?,?)",
                             (str(uuid.uuid4()), frame.id, normalized, json.dumps(box), mask, score, spatial.model_dump_json()))
        conn.commit()
    finally:
        conn.close()
    return QueryResponse(
        state=state,
        bbox=latest_box,
        mask=latest_mask,
        trail=trail,
        answer=answer,
        query=original_query,
        frame_path=latest_frame.frame_path,
        frame_id=latest_frame.id,
    )
