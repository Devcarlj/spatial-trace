"""Extract timestamped review frames and contact sheets without model calls."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        parser.error("Cannot open source video")
    fps = capture.get(cv2.CAP_PROP_FPS)
    count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0 or count <= 0:
        parser.error("Source has invalid frame metadata")
    args.output.mkdir(parents=True, exist_ok=True)
    indices = sorted(set(range(0, count, max(1, round(args.interval * fps)))) | {count - 1})
    records, tiles = [], []
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"Cannot decode frame {index}")
            filename = f"frame_{index:06d}.jpg"
            if not cv2.imwrite(str(args.output / filename), frame):
                raise RuntimeError(f"Cannot write {filename}")
            tile = np.zeros((200, 330, 3), dtype=np.uint8)
            scale = min(330 / frame.shape[1], 174 / frame.shape[0])
            thumb = cv2.resize(frame, None, fx=scale, fy=scale)
            tile[:thumb.shape[0], :thumb.shape[1]] = thumb
            cv2.putText(tile, f"{index / fps:.3f}s  frame {index}", (6, 192),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
            tiles.append(tile)
            records.append({"frame_index": index, "timestamp": index / fps, "file": filename})
    finally:
        capture.release()
    for start in range(0, len(tiles), 24):
        page = tiles[start:start + 24]
        page += [np.zeros_like(tiles[0])] * ((-len(page)) % 4)
        sheet = np.vstack([np.hstack(page[i:i + 4]) for i in range(0, len(page), 4)])
        cv2.imwrite(str(args.output / f"sheet_{start // 24 + 1}.jpg"), sheet)
    with args.video.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    metadata = {"source_name": args.video.name, "sha256": digest, "fps": fps,
                "frame_count": count, "duration_seconds": count / fps,
                "review_interval_seconds": args.interval, "frames": records}
    (args.output / "review.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "frames": len(records), "sha256": digest}))


if __name__ == "__main__":
    main()
