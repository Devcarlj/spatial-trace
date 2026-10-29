from core.contracts import SamResponse
from core.providers import get_model_client


def get_cache_key(endpoint, payload):
    from core.cache import cache_key

    return cache_key(endpoint, payload)


def check_cache(cache_key_value):
    from core.cache import get_cached

    return get_cached(cache_key_value)


def save_to_cache(cache_key_value, response_data):
    from core.cache import set_cached

    set_cached(cache_key_value, response_data)


async def call_sam_image_endpoint(image_path, noun_phrase) -> dict:
    """
    Calls SAM 3.1 Image Endpoint with one noun phrase per call.
    Uses the shared ModelClient (mock or live, plus dual cache).
    """
    result: SamResponse = get_model_client().sam_segment(image_path, noun_phrase)
    return result.model_dump()
