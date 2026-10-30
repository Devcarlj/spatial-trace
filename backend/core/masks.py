"""Decode SAM's base85 masks with Meta's official codec; preserve exact pixels."""

import base64
import re

import cv2
import numpy as np
from meta_sam_parser import InvalidSegmentationMaskError, SegmentationMask, decode_mask_to_raster

from core.contracts import MaskOverlay

MAX_MASK_PIXELS = 16_000_000


def decode_mask(token: str | None) -> np.ndarray | None:
    if not token:
        return None
    match = re.fullmatch(r"<\|mask;[^|]*?data=(\d+),(\d+),([!~][^|]+)\|>", token)
    if not match:
        return None
    height, width = int(match[1]), int(match[2])
    if not 0 < height * width <= MAX_MASK_PIXELS:
        return None
    try:
        mask = SegmentationMask(
            encoding="one_bit" if match[3][0] == "!" else "lossless",
            payload=match[3], width=width, height=height,
        )
        return np.frombuffer(decode_mask_to_raster(mask), dtype=np.uint8).reshape(height, width)
    except (InvalidSegmentationMaskError, ValueError, OverflowError):
        # Old snapshots, mock URI tokens, and corrupt masks still get box evidence.
        return None


def mask_overlay(token: str | None, bbox: list[float]) -> MaskOverlay | None:
    raster = decode_mask(token)
    if raster is None:
        return None
    height, width = raster.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, :3] = (135, 236, 168)  # BGRA for OpenCV's PNG encoder
    rgba[:, :, 3] = raster * 115
    ok, png = cv2.imencode(".png", rgba)
    if not ok:
        return None
    return MaskOverlay(data_url="data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                       bbox=bbox, width=width, height=height)
