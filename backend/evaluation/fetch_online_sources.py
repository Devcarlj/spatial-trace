"""Download the openly-licensed online clips used by the Milestone 1 manifests.

Files land in the ignored backend/data/evaluation/online-sources/final folder
(see ONLINE_SOURCES.md for provenance, hashes, and labeling limits). The tiny
coin clip is additionally trimmed to 0-20s; trimming is documented in
online_tiny_objects.json and must be redone with OpenCV if re-downloaded.
"""
import urllib.request
from pathlib import Path

CLIPS = {
    "online_static_camera.mp4": "https://assets.mixkit.co/videos/4806/4806-1080.mp4",
    "online_handheld_pan.mp4": "https://assets.mixkit.co/qz3dcv4dpqssphzjl0zi11yv9ulu",
    "online_lighting_change.mp4": "https://assets.mixkit.co/videos/45366/45366-720.mp4",
    "online_occlusion.mp4": "https://assets.mixkit.co/videos/47017/47017-720.mp4",
    "online_similar_items.mp4": "https://assets.mixkit.co/videos/18263/18263-1080.mp4",
    "online_tiny_objects.mp4": "https://assets.mixkit.co/videos/31100/31100-720.mp4",
}

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "online-sources" / "final"
    out.mkdir(parents=True, exist_ok=True)
    for name, url in CLIPS.items():
        target = out / name
        if target.exists():
            print(f"skip {name}")
            continue
        request = urllib.request.Request(url, headers={"User-Agent": "SpatialTrace-Eval/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as file:
            file.write(response.read())
        print(f"downloaded {name} ({target.stat().st_size} bytes) from {url}")
