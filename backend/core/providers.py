"""Model I/O: interfaces, mock fixtures, fail-closed live stubs, cached client."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests
from pydantic import ValidationError

from core.cache import cached_call
from core.contracts import QueryResponse, SamResponse, SpatialJson, VlmIndexOutput
from core.settings import Settings, get_settings

SYNONYM_MAP = {
    "specs": "reading glasses",
    "glasses": "reading glasses",
    "shades": "black sunglasses",
}


class ProviderUnavailable(RuntimeError):
    """Live provider refused to call the network (missing key, 401, or similar)."""


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
        self.attempts[name] = self.attempts.get(name, 0) + 1
        if name == "bad_then_good.jpg" and self.attempts[name] == 1:
            return "{not valid json"
        if name in self.fixtures:
            return self.fixtures[name]
        return self.default_json


class MockLlmProvider(LlmProvider):
    def normalize_query(self, query: str) -> str:
        words = query.strip().lower()
        for src, dest in SYNONYM_MAP.items():
            if src in words:
                return dest
        return query.strip()

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
        _require_live_key(self.settings)
        url = f"{self.settings.sam_base_url.rstrip('/')}/segment"
        try:
            response = requests.post(
                url,
                headers=_auth_headers(self.settings),
                json={
                    "model": self.settings.sam_model_name,
                    "image_path": image_path,
                    "prompt": noun_phrase,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ProviderUnavailable(f"Live SAM request failed closed: {exc}") from exc
        _raise_if_blocked(response, "SAM")
        return SamResponse.model_validate(response.json()).model_dump()


class LiveVlmProvider(VlmProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def describe_crop(self, crop_path: str) -> str:
        _require_live_key(self.settings)
        url = f"{self.settings.sam_base_url.rstrip('/')}/vlm"
        try:
            response = requests.post(
                url,
                headers=_auth_headers(self.settings),
                json={"model": self.settings.vlm_model_name, "crop_path": crop_path},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ProviderUnavailable(f"Live VLM request failed closed: {exc}") from exc
        _raise_if_blocked(response, "VLM")
        if response.headers.get("content-type", "").startswith("application/json"):
            return json.dumps(response.json())
        return response.text


class LiveLlmProvider(LlmProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def normalize_query(self, query: str) -> str:
        data = self._post("/llm/normalize", {"query": query, "model": self.settings.llm_model_name})
        return str(data.get("normalized", query))

    def describe_spatial(self, crop_path: str, noun_phrase: str) -> dict[str, Any]:
        data = self._post(
            "/llm/spatial",
            {
                "crop_path": crop_path,
                "noun": noun_phrase,
                "model": self.settings.llm_model_name,
            },
        )
        return SpatialJson.model_validate(data).model_dump()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        _require_live_key(self.settings)
        url = f"{self.settings.sam_base_url.rstrip('/')}{path}"
        try:
            response = requests.post(
                url,
                headers=_auth_headers(self.settings),
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise ProviderUnavailable(f"Live LLM request failed closed: {exc}") from exc
        _raise_if_blocked(response, "LLM")
        return response.json()


def _auth_headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.model_api_key}",
        "Content-Type": "application/json",
    }


def _require_live_key(settings: Settings) -> None:
    if not settings.live_key_ready:
        raise ProviderUnavailable(
            "Live APIs fail closed: set a real MODEL_API_KEY (not the placeholder)."
        )


def _raise_if_blocked(response: requests.Response, label: str) -> None:
    if response.status_code == 401:
        raise ProviderUnavailable(
            f"Live {label} blocked (401). Keep SPATIALTRACE_MODE=mock until the portal key works."
        )
    if response.status_code >= 400:
        raise ProviderUnavailable(
            f"Live {label} failed closed with HTTP {response.status_code}."
        )


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
                    parsed = json.loads(raw)
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
