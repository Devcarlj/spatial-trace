"""Unified env loading and pipeline thresholds.

`SPATIALTRACE_MODE=mock|live` is the only switch between fixture providers
and live HTTP stubs. `OFFLINE_SNAPSHOTS` is reserved for Stage 3 replay JSON.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name, default)
    if raw is None:
        return None
    return raw.strip().strip("\"'")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None or raw == "":
        return default
    return int(raw)


class Settings(BaseModel):
    spatialtrace_mode: str = "mock"
    offline_snapshots: bool = False
    model_api_key: str = ""
    sam_base_url: str = "https://api.meta.ai/v1"
    sam_model_name: str = "sam-3.1"
    vlm_model_name: str = "cheap-vlm"
    llm_model_name: str = "muse-spark"
    data_dir: Path = Field(default_factory=lambda: BACKEND_DIR / "data")

    settle_spike_threshold: float = 500_000.0
    settle_calm_threshold: float = 100_000.0
    settle_calm_frames: int = 6
    min_diff_area: int = 500

    sam_score_high: float = 0.80
    sam_score_mid: float = 0.40

    recall_frame_count: int = 8
    parallel_candidate_count: int = 5

    @field_validator("spatialtrace_mode")
    @classmethod
    def _mode_ok(cls, value: str) -> str:
        mode = value.lower()
        if mode not in {"mock", "live"}:
            raise ValueError("SPATIALTRACE_MODE must be 'mock' or 'live'")
        return mode

    @property
    def db_path(self) -> Path:
        return self.data_dir / "spatialtrace.db"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def live_key_ready(self) -> bool:
        key = self.model_api_key.strip()
        return bool(key) and not key.upper().startswith("YOUR_")


def load_settings() -> Settings:
    data_dir_raw = _env("SPATIALTRACE_DATA_DIR")
    return Settings(
        spatialtrace_mode=_env("SPATIALTRACE_MODE", "mock") or "mock",
        offline_snapshots=_env_bool("OFFLINE_SNAPSHOTS", False),
        model_api_key=_env("MODEL_API_KEY", "") or "",
        sam_base_url=_env("SAM_BASE_URL", "https://api.meta.ai/v1") or "https://api.meta.ai/v1",
        sam_model_name=_env("SAM_MODEL_NAME", "sam-3.1") or "sam-3.1",
        vlm_model_name=_env("VLM_MODEL_NAME", "cheap-vlm") or "cheap-vlm",
        llm_model_name=_env("LLM_MODEL_NAME", "muse-spark") or "muse-spark",
        data_dir=Path(data_dir_raw) if data_dir_raw else BACKEND_DIR / "data",
        settle_spike_threshold=_env_float("SETTLE_SPIKE_THRESHOLD", 500_000.0),
        settle_calm_threshold=_env_float("SETTLE_CALM_THRESHOLD", 100_000.0),
        settle_calm_frames=_env_int("SETTLE_CALM_FRAMES", 6),
        min_diff_area=_env_int("MIN_DIFF_AREA", 500),
        sam_score_high=_env_float("SAM_SCORE_HIGH", 0.80),
        sam_score_mid=_env_float("SAM_SCORE_MID", 0.40),
        recall_frame_count=_env_int("RECALL_FRAME_COUNT", 8),
        parallel_candidate_count=_env_int("PARALLEL_CANDIDATE_COUNT", 5),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reset_settings() -> None:
    get_settings.cache_clear()
