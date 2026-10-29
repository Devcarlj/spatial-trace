from core.cache import cache_key, cached_call, get_cached, set_cached
from core.settings import get_settings


def test_cache_miss_then_hit_sqlite_and_disk(isolated_env):
    calls = {"n": 0}

    def produce():
        calls["n"] += 1
        return {"ok": True, "n": calls["n"]}

    first = cached_call("unit", {"x": 1}, produce)
    second = cached_call("unit", {"x": 1}, produce)

    assert first == {"ok": True, "n": 1}
    assert second == first
    assert calls["n"] == 1

    key = cache_key("unit", {"x": 1})
    disk = get_settings().cache_dir / f"{key}.json"
    assert disk.exists()
    assert get_cached(key) == first


def test_cache_key_is_stable_for_equal_payloads(isolated_env):
    a = cache_key("sam_image", {"prompt": "keys", "image_path": "a.jpg"})
    b = cache_key("sam_image", {"image_path": "a.jpg", "prompt": "keys"})
    c = cache_key("sam_image", {"prompt": "mug", "image_path": "a.jpg"})
    assert a == b
    assert a != c


def test_set_cached_mirrors_to_disk(isolated_env):
    key = cache_key("probe", {"id": 7})
    set_cached(key, {"hello": "world"})
    disk = get_settings().cache_dir / f"{key}.json"
    assert disk.read_text(encoding="utf-8") == '{"hello": "world"}'
    assert get_cached(key) == {"hello": "world"}
