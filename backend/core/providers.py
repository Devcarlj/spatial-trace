"""Model I/O: fixture providers and documented Meta Responses adapters."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.cache import cached_call
from core.contracts import QueryResponse, SamResponse, SpatialJson, VlmIndexOutput
from core.settings import Settings, get_settings
from core.live_transport import ProviderUnavailable, responses, parse_json, parse_segmentation
from core.demo_fixtures import DEMO_SEGMENTATIONS

SYNONYM_MAP = {
    "specs": "reading glasses",
    "glasses": "reading glasses",
    "shades": "black sunglasses",
}


class SamProvider(ABC):
    @abstractmethod
    def segment(self, image_path: str, noun_phrase: str) -> dict[str, Any]:
        raise NotImplementedError


class VlmProvider(ABC):
    @abstractmethod
    def describe_crop(self, crop_path: str) -> str:
        """Return a JSON string (possibly invalid — caller validates and retries)."""
        raise NotImplementedError


class LlmProvider(ABC):
    @abstractmethod
    def normalize_query(self, query: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def describe_spatial(self, crop_path: str, noun_phrase: str) -> dict[str, Any]:
        raise NotImplementedError


class MockSamProvider(SamProvider):
    """Fixture boxes/masks/scores keyed by (image stem, noun)."""

    fixtures: dict[tuple[str, str], dict[str, Any]] = {
        **DEMO_SEGMENTATIONS,
        ("desk_frame_01", "reading glasses"): {
            "boxes": [[120.0, 80.0, 260.0, 160.0]],
            "scores": [0.93],
            "masks": ["mock://desk_frame_01/reading_glasses"],
        },
        ("desk_frame_01", "keys"): {
            "boxes": [[40.0, 200.0, 90.0, 240.0]],
            "scores": [0.88],
            "masks": ["mock://desk_frame_01/keys"],
        },
        ("desk_frame_moved", "reading glasses"): {
            "boxes": [[400.0, 90.0, 520.0, 170.0]],
            "scores": [0.91],
            "masks": ["mock://desk_frame_moved/reading_glasses"],
        },
        ("desk_frame_unsure", "mug"): {
            "boxes": [[10.0, 10.0, 80.0, 90.0]],
            "scores": [0.51],
            "masks": ["mock://desk_frame_unsure/mug"],
        },
    }
    default_response: dict[str, Any] = {
        "boxes": [[100.0, 100.0, 200.0, 200.0]],
        "scores": [0.35],
        "masks": ["mock://default"],
    }

    def segment(self, image_path: str, noun_phrase: str) -> dict[str, Any]:
        image_id = Path(image_path).stem
        noun = noun_phrase.strip().lower()
        payload = self.fixtures.get((image_id, noun), self.default_response)
        return SamResponse.model_validate(payload).model_dump()


class MockVlmProvider(VlmProvider):
    """Fixture JSON per crop filename. `bad_then_good.jpg` fails once, then succeeds."""

    fixtures: dict[str, str] = {
        "crop_desk.jpg": json.dumps(
            {
                "objects": ["reading glasses", "keys", "book"],
                "caption": "Reading glasses and keys on a wooden desk.",
            }
        ),
        "bad_then_good.jpg": json.dumps(
            {
                "objects": ["reading glasses"],
                "caption": "A pair of reading glasses after retry.",
            }
        ),
        "always_bad.jpg": "not-json",
    }
    default_json = json.dumps(
        {
            "objects": ["keys", "black sunglasses", "book"],
            "caption": "A pair of black sunglasses and keys resting on a wooden desk.",
        }
    )

    def __init__(self) -> None:
        self.attempts: dict[str, int] = {}

    def describe_crop(self, crop_path: str) -> str:
        name = Path(crop_path).name
        for (stem, noun) in DEMO_SEGMENTATIONS:
            if Path(crop_path).stem == stem:
                return json.dumps({"objects": [noun], "caption": f"Synthetic demo: {noun} on a textured desk."})
        self.attempts[name] = self.attempts.get(name, 0) + 1
        if name == "bad_then_good.jpg" and self.attempts[name] == 1:
            return "{not valid json"
        if name in self.fixtures:
            return self.fixtures[name]
        return self.default_json


class MockLlmProvider(LlmProvider):
    def normalize_query(self, query: str) -> str:
        words = query.strip().lower().rstrip("?.! ")
        words = re.sub(r"^(?:(?:where (?:is|are)|find|locate|show)(?: me)?\s+)?(?:(?:my|the|a|an)\s+)?", "", words)
        for src, dest in SYNONYM_MAP.items():
            if re.search(r"\b" + re.escape(src) + r"\b", words):
                return dest
        return words

    def describe_spatial(self, crop_path: str, noun_phrase: str) -> dict[str, Any]:
        payload = {
            "surface": "wooden desk",
            "anchor": f"near the {noun_phrase}" if noun_phrase else "near the object",
            "visibility": "fully visible",
        }
        return SpatialJson.model_validate(payload).model_dump()


class LiveSamProvider(SamProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def segment(self, image_path: str, noun_phrase: str) -> dict[str, Any]:
        return parse_segmentation(responses(self.settings, self.settings.sam_model_name,
                                            noun_phrase, image_path, segmentation=True))



class LiveVlmProvider(VlmProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def describe_crop(self, crop_path: str) -> str:
        return responses(self.settings, self.settings.vlm_model_name,
                         'Identify visible objects. Return only JSON: {"objects": [string], "caption": string}.',
                         crop_path)



class LiveLlmProvider(LlmProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def normalize_query(self, query: str) -> str:
        text = responses(self.settings, self.settings.llm_model_name,
                         'Extract the single object noun phrase being sought. Expand synonyms. '
                         'Return only JSON {"normalized": string}. Query: ' + query)
        normalized = parse_json(text).get("normalized", "").strip()
        if not normalized:
            raise ProviderUnavailable("Normalizer returned an empty object phrase.")
        return normalized

    def describe_spatial(self, crop_path: str, noun_phrase: str) -> dict[str, Any]:
        data = parse_json(responses(self.settings, self.settings.llm_model_name,
                         'Describe the visible location of ' + noun_phrase +
                         '. Return only JSON with string fields surface, anchor, visibility.', crop_path))
        return SpatialJson.model_validate(data).model_dump()



def build_providers(settings: Settings | None = None) -> tuple[SamProvider, VlmProvider, LlmProvider]:
    settings = settings or get_settings()
    if settings.spatialtrace_mode == "live":
        return LiveSamProvider(settings), LiveVlmProvider(settings), LiveLlmProvider(settings)
    return MockSamProvider(), MockVlmProvider(), MockLlmProvider()


class ModelClient:
    """Single entry point for SAM / VLM / LLM. Cache wraps successful calls only."""

    def __init__(
        self,
        sam: SamProvider,
        vlm: VlmProvider,
        llm: LlmProvider,
        settings: Settings | None = None,
    ) -> None:
        self.sam = sam
        self.vlm = vlm
        self.llm = llm
        self.settings = settings or get_settings()

    def sam_segment(self, image_path: str, noun_phrase: str) -> SamResponse:
        payload = {"image_path": image_path, "prompt": noun_phrase}
        raw = cached_call("sam_image", payload, lambda: self.sam.segment(image_path, noun_phrase))
        return SamResponse.model_validate(raw)

    def vlm_describe(self, crop_path: str) -> VlmIndexOutput:
        payload = {"crop_path": crop_path}

        def _call() -> dict[str, Any]:
            last_error: Exception | None = None
            for _ in range(2):
                raw = self.vlm.describe_crop(crop_path)
                try:
                    parsed = parse_json(raw)
                    return VlmIndexOutput.model_validate(parsed).model_dump()
                except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                    last_error = exc
            raise last_error or ValueError("VLM output failed schema validation")

        return VlmIndexOutput.model_validate(cached_call("cheap_vlm", payload, _call))

    def normalize_query(self, query: str) -> str:
        payload = {"query": query}
        return cached_call("llm_normalize", payload, lambda: self.llm.normalize_query(query))

    def describe_spatial(self, crop_path: str, noun_phrase: str) -> SpatialJson:
        payload = {"crop_path": crop_path, "noun": noun_phrase}
        raw = cached_call(
            "llm_spatial",
            payload,
            lambda: self.llm.describe_spatial(crop_path, noun_phrase),
        )
        return SpatialJson.model_validate(raw)


@lru_cache(maxsize=1)
def get_model_client() -> ModelClient:
    settings = get_settings()
    sam, vlm, llm = build_providers(settings)
    return ModelClient(sam, vlm, llm, settings)


# Re-export for callers that only need the query contract.
__all__ = [
    "LlmProvider",
    "LiveLlmProvider",
    "LiveSamProvider",
    "LiveVlmProvider",
    "MockLlmProvider",
    "MockSamProvider",
    "MockVlmProvider",
    "ModelClient",
    "ProviderUnavailable",
    "QueryResponse",
    "SamProvider",
    "VlmProvider",
    "build_providers",
    "get_model_client",
]
