import httpx
import pytest
import respx

from app.auth import TokenManager
from app.config import Settings
from app.models import Footprint, ProductType
from app.services.cache import cache_footprint, cache_sensing_time
from app.services.render import footprint_bbox, render_product_image


def test_footprint_bbox_returns_min_max_lon_lat():
    footprint = Footprint(
        coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0], [95.0, 4.0]]]
    )
    assert footprint_bbox(footprint) == [95.0, 4.0, 98.0, 6.0]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        cdse_identity_url="https://identity.test/token",
        cdse_process_url="https://process.test/api/v1/process",
    )


async def test_render_product_image_rejects_slc(settings):
    token_manager = TokenManager(settings)
    cache_footprint(
        "slc-product-1", Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0]]])
    )
    cache_sensing_time("slc-product-1", "2026-01-26T11:43:01.722106Z")

    with pytest.raises(ValueError, match="GRD"):
        await render_product_image("slc-product-1", ProductType.SLC, settings, token_manager)


async def test_render_product_image_rejects_l1c(settings):
    token_manager = TokenManager(settings)
    cache_footprint(
        "l1c-product-1", Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0]]])
    )
    cache_sensing_time("l1c-product-1", "2026-01-26T11:43:01.722106Z")

    with pytest.raises(ValueError, match="L2A"):
        await render_product_image("l1c-product-1", ProductType.S2_L1C, settings, token_manager)


@respx.mock
async def test_render_product_image_posts_correct_body_for_s2_l2a(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    process_route = respx.post("https://process.test/api/v1/process").mock(
        return_value=httpx.Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
    )

    cache_footprint(
        "l2a-product-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0], [95.0, 4.0]]]),
    )
    cache_sensing_time("l2a-product-1", "2026-01-26T11:43:01.722106Z")
    token_manager = TokenManager(settings)

    image_bytes = await render_product_image(
        "l2a-product-1", ProductType.S2_L2A, settings, token_manager
    )

    assert image_bytes == b"fake-png-bytes"
    sent_body = process_route.calls.last.request.content
    import json

    payload = json.loads(sent_body)
    assert payload["input"]["data"][0]["type"] == "sentinel-2-l2a"
    assert "B04" in payload["evalscript"]


async def test_render_product_image_raises_when_not_cached(settings):
    token_manager = TokenManager(settings)
    with pytest.raises(ValueError, match="No cached data"):
        await render_product_image("never-searched", ProductType.GRD, settings, token_manager)


@respx.mock
async def test_render_product_image_posts_correct_body_and_returns_bytes(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    process_route = respx.post("https://process.test/api/v1/process").mock(
        return_value=httpx.Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
    )

    cache_footprint(
        "grd-product-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0], [95.0, 4.0]]]),
    )
    cache_sensing_time("grd-product-1", "2026-01-26T11:43:01.722106Z")
    token_manager = TokenManager(settings)

    image_bytes = await render_product_image(
        "grd-product-1", ProductType.GRD, settings, token_manager
    )

    assert image_bytes == b"fake-png-bytes"
    sent_body = process_route.calls.last.request.content
    import json

    payload = json.loads(sent_body)
    assert payload["input"]["data"][0]["type"] == "sentinel-1-grd"
    assert payload["input"]["bounds"]["bbox"] == [95.0, 4.0, 98.0, 6.0]
    assert payload["input"]["data"][0]["dataFilter"]["timeRange"] == {
        "from": "2026-01-26T00:00:00Z",
        "to": "2026-01-26T23:59:59Z",
    }
    assert "VV" in payload["evalscript"]
