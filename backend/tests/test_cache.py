from app.services.cache import cache_product_size, get_cached_product_size


def test_get_cached_product_size_returns_none_when_never_cached():
    assert get_cached_product_size("never-cached-size-id") is None


def test_cache_product_size_roundtrip():
    cache_product_size("size-cache-p1", "1632MB")
    assert get_cached_product_size("size-cache-p1") == "1632MB"
