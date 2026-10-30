"""Documented Meta Responses transport. Never sends server-local paths.

References: dev.meta.ai/docs/image-understanding and /sam/segmenting.
"""
import base64
import json
import re
import math
from pathlib import Path

import requests


class ProviderUnavailable(RuntimeError):
    pass


def responses(settings, model, prompt, image_path=None, segmentation=False):
    if not settings.live_key_ready:
        raise ProviderUnavailable("Live APIs fail closed: set a real MODEL_API_KEY.")
    content = [{"type": "input_text", "text": prompt}]
    if image_path:
        path = Path(image_path)
        if not path.is_file():
            raise ProviderUnavailable("Provider input image does not exist.")
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"})
    payload = {"model": model, "input": [{"type": "message", "role": "user", "content": content}],
               "stream": segmentation, "store": False}
    if segmentation:
        payload["metadata"] = {"include_confidence": "true", "mask_encoding": "one_bit"}
    else:
        payload["max_output_tokens"] = 2048
    try:
        with requests.post(f"{settings.sam_base_url.rstrip('/')}/responses",
                           headers={"Authorization": f"Bearer {settings.model_api_key}",
                                    "Content-Type": "application/json"},
                           json=payload, timeout=(10, 120), stream=segmentation) as response:
            if response.status_code >= 400:
                # Do not echo response bodies: they can include inputs or credentials.
                raise ProviderUnavailable(f"Live model {model} returned HTTP {response.status_code}; check model access and configuration.")
            if segmentation:
                parts, completed = [], False
                for line in response.iter_lines():
                    if not line.startswith(b"data:"):
                        continue
                    data = line[5:].strip()
                    if data == b"[DONE]":
                        break
                    event = json.loads(data)
                    if event.get("type") == "response.output_text.delta":
                        parts.append(event.get("delta", ""))
                    elif event.get("type") == "response.completed":
                        completed = True
                    elif event.get("type") in {"error", "response.failed", "response.incomplete"}:
                        raise ProviderUnavailable("Live segmentation stream failed.")
                if not completed:
                    raise ProviderUnavailable("Live segmentation stream ended before completion.")
                return "".join(parts)
            result = response.json()
            if result.get("error") or result.get("status") not in {None, "completed"}:
                raise ProviderUnavailable("Live response did not complete.")
            text = "".join(c.get("text", "") for item in result.get("output", [])
                           for c in item.get("content", []) if c.get("type") in {"output_text", "text"})
            if not text:
                raise ProviderUnavailable("Live response contained no text.")
            return text
    except requests.RequestException as exc:
        raise ProviderUnavailable("Live provider connection failed or timed out.") from exc


def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


def parse_segmentation(text):
    boxes, scores, masks = [], [], []
    image_size = None
    for match in re.finditer(r"<\|box;([^|]+)\|>(<\|mask;.*?\|>)", text):
        fields = dict(field.split("=", 1) for field in match[1].split(";"))
        if "c" not in fields:
            raise ProviderUnavailable("SAM response omitted requested confidence.")
        try:
            box = [float(fields[key]) for key in ("x1", "y1", "x2", "y2")]
            score = float(fields["c"])
            size = [int(fields["w"]), int(fields["h"])]
        except (KeyError, ValueError) as exc:
            raise ProviderUnavailable("Invalid SAM box geometry.") from exc
        if (not all(math.isfinite(value) for value in [*box, score]) or not 0 <= score <= 1
                or min(size) <= 0 or not 0 <= box[0] <= box[2] < size[0]
                or not 0 <= box[1] <= box[3] < size[1] or image_size not in (None, size)):
            raise ProviderUnavailable("Invalid SAM box geometry or confidence.")
        # SAM wire corners are inclusive; all internal boxes are half-open.
        boxes.append([box[0], box[1], box[2] + 1, box[3] + 1])
        scores.append(score)
        masks.append(match[2])
        image_size = size
    if text.strip() and not boxes:
        raise ProviderUnavailable("Unrecognized SAM segmentation output.")
    result = {"boxes": boxes, "scores": scores, "masks": masks}
    if image_size:
        result["image_size"] = image_size
    return result
