"""Small redacted live check: python live_check.py [image_path]."""
import sys
from core.providers import get_model_client
from core.settings import get_settings

def main():
    settings = get_settings()
    print(f"mode={settings.spatialtrace_mode}; vision={settings.vlm_model_name}; text={settings.llm_model_name}")
    client = get_model_client()
    if settings.spatialtrace_mode != "live":
        print("Set SPATIALTRACE_MODE=live to run the live check.")
        return 2
    try:
        print("normalized:", client.normalize_query("Where are the glasses?"))
        if len(sys.argv) > 1:
            print("vision:", client.vlm_describe(sys.argv[1]).model_dump())
            result = client.sam_segment(sys.argv[1], "glasses")
            print("segmentation:", {"boxes": result.boxes, "scores": result.scores})
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc))
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
