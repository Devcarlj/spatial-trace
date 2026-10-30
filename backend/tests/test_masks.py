import base64

import cv2
import numpy as np
import pytest

from core.demo_fixtures import GLASSES_MASK, KEYS_MASK, MUG_MASK
from core.masks import decode_mask, mask_overlay


@pytest.mark.parametrize("token,shape", [(GLASSES_MASK, (80, 140)), (KEYS_MASK, (40, 50)), (MUG_MASK, (80, 70))])
def test_masks_decode_exact_non_rectangular_silhouettes(token, shape):
    raster = decode_mask(token)
    assert raster.shape == shape
    assert 0 < raster.sum() < raster.size
    overlay = mask_overlay(token, [100, 200, 100 + shape[1], 200 + shape[0]])
    png = base64.b64decode(overlay.data_url.split(",", 1)[1])
    rgba = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert np.array_equal(rgba[:, :, 3], raster * 115)
    assert overlay.bbox[:2] == [100, 200]


def test_lossless_encoding_supported():
    token = "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
    raster = decode_mask(token)
    assert raster.shape == (27, 60)
    assert 0 < raster.sum() < raster.size


@pytest.mark.parametrize("token", [None, "mock://old-mask", "<|mask;x=0;y=0;data=2,2,!broken|>",
                                   "<|mask;x=0;y=0;data=100000,100000,!a|>"])
def test_invalid_or_oversized_mask_falls_back_to_box(token):
    assert mask_overlay(token, [0, 0, 20, 20]) is None
