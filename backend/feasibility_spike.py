import base64

from core.providers import ProviderUnavailable, get_model_client
from core.settings import get_settings


def test_sam_endpoint(image_path, noun_phrase):
    settings = get_settings()
    print(f"Testing SAM 3.1 Image Endpoint for: '{noun_phrase}' on {image_path}")
    print(f"Mode={settings.spatialtrace_mode} model={settings.sam_model_name}")

    if settings.spatialtrace_mode == "live":
        with open(image_path, "rb") as image_file:
            base64.b64encode(image_file.read()).decode("utf-8")

    try:
        data = get_model_client().sam_segment(image_path, noun_phrase)
    except ProviderUnavailable as exc:
        print(f"Provider unavailable (fail closed): {exc}")
        return None

    print("\n--- API Response ---")
    print(f"Boxes: {data.boxes}")
    print(f"Scores: {data.scores}")
    print("Masks returned:", len(data.masks) > 0)
    return data.model_dump()


if __name__ == "__main__":
    # Point this at a crop once Stage 2 has indexed a clip.
    # test_sam_endpoint("data/frames/clip_desk_01/crop_120.jpg", "keys")
    pass
