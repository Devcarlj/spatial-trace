"""Generate synthetic stills/clips and seed an isolated, repeatable mock demo.

Run with SPATIALTRACE_MODE=mock and a dedicated SPATIALTRACE_DATA_DIR.
No external assets or live model calls are used.
"""

import json
import sqlite3

import cv2
import numpy as np

from core.demo_fixtures import DEMO_SEGMENTATIONS
from core.masks import decode_mask
from core.query_service import query_memory
from core.settings import get_settings
from core.vlm_client import index_settled_frame
from database import init_db


def generate_demo() -> dict:
    settings = get_settings()
    if settings.spatialtrace_mode != "mock" or settings.offline_snapshots:
        raise ValueError("Demo generation requires SPATIALTRACE_MODE=mock and OFFLINE_SNAPSHOTS=0.")
    init_db()
    folder = settings.data_dir / "frames" / "synthetic-demo"
    folder.mkdir(parents=True, exist_ok=True)
    # A repeatable textured background gives the camera estimator real features.
    rng = np.random.default_rng(42)
    background = np.full((512, 768, 3), (180, 200, 215), dtype=np.uint8)
    for _ in range(500):
        point = tuple(int(value) for value in rng.integers([5, 5], [763, 507]))
        color = tuple(int(value) for value in rng.integers(60, 170, size=3))
        cv2.circle(background, point, int(rng.integers(1, 4)), color, -1)
    groups: dict[str, list[np.ndarray]] = {}
    for (stem, noun), detection in DEMO_SEGMENTATIONS.items():
        clip = "synthetic-" + ("glasses" if "glasses" in stem else "keys" if "keys" in stem else "mug")
        path = folder / f"{stem}.png"
        image = background.copy()
        x1, y1, x2, y2 = detection["boxes"][0]
        mask = decode_mask(detection["masks"][0])
        image[y1:y2, x1:x2][mask.astype(bool)] = (35, 65, 210)
        if not cv2.imwrite(str(path), image):
            raise OSError("Could not write demo still")
        groups.setdefault(clip, []).append(image)
        with sqlite3.connect(settings.db_path) as conn:
            exists = conn.execute("SELECT id FROM frames WHERE frame_path=?", (str(path),)).fetchone()
        if not exists:
            index_settled_frame(clip, 1.0 if stem.endswith("01") else 4.0, str(path), str(path), [0, 0, 768, 512])
    video_folder = settings.data_dir / "demo-clips"
    video_folder.mkdir(parents=True, exist_ok=True)
    for clip, images in groups.items():
        writer = cv2.VideoWriter(str(video_folder / f"{clip}.avi"), cv2.VideoWriter_fourcc(*"MJPG"), 3, (768, 512))
        if not writer.isOpened():
            raise OSError("Could not create demo video")
        try:
            for image in images:
                for _ in range(9):
                    writer.write(image)
        finally:
            writer.release()
    scenarios = {"keys": "FOUND_NOW", "where are my specs": "MOVED", "mug": "UNSURE"}
    results = {}
    for query, expected in scenarios.items():
        result = query_memory(query)
        if result.state != expected or result.mask_overlay is None:
            raise AssertionError(f"Demo {query}: expected {expected} with mask, got {result.state}")
        results[query] = {"expected": expected, "state": result.state, "observations": len(result.trail)}
    manifest = {"synthetic": True, "scenarios": results, "video_directory": str(video_folder.resolve())}
    (settings.data_dir / "demo-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(generate_demo(), indent=2))
