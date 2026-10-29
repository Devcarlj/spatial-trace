"""Validate Meta Model API credentials without invoking the pipeline.

Run from ``backend`` while the real ``MODEL_API_KEY`` is present in ``.env``:

    python api_smoke_test.py

The script deliberately makes one small image-generation request through
Meta's Responses API. It never prints the key, image bytes, or a complete
response body, so it is safe to use in a terminal or CI log.
"""

from __future__ import annotations

import sys

import requests

from core.settings import get_settings


def main() -> int:
    settings = get_settings()
    if not settings.live_key_ready:
        print("MODEL_API_KEY is missing or still a placeholder.")
        return 2

    url = f"{settings.sam_base_url.rstrip('/')}/responses"
    payload = {
        "input": [
            {
                "content": [
                    {
                        "text": "Generate a tiny blue circle on a plain white background.",
                        "type": "input_text",
                    }
                ],
                "role": "user",
                "type": "message",
            }
        ],
        "max_output_tokens": 2048,
        "model": "muse-image-1.0",
        "store": True,
        "stream": False,
        "temperature": 0.6,
        "top_p": 0.9,
        "tools": [
            {
                "enable_image_search": True,
                "enable_shell": True,
                "enable_web_search": True,
                "output_format": "png",
                "reasoning_strength": "high",
                "type": "image_generation",
            }
        ],
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.model_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=300,
        )
    except requests.RequestException as exc:
        print(f"API smoke test could not reach the provider: {exc}")
        return 1

    if response.ok and response.json().get("status") == "completed":
        print(
            "API smoke test passed "
            "(HTTP 200; model=muse-image-1.0; Responses API)."
        )
        return 0

    if response.ok:
        print("API smoke test returned HTTP 200 but did not complete successfully.")
        return 1

    print(f"API smoke test failed (HTTP {response.status_code}).")
    if response.status_code in {401, 403}:
        print("The provider rejected the configured credential or its permissions.")
    else:
        print("The key was not exposed; inspect the provider endpoint/model configuration.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
