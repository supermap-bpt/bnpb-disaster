import httpx
import pytest
import respx

from app.models import Footprint, ProductType
from app.services.cache import (
    cache_footprint,
    cache_product_type,
    cache_quicklook_asset_id,
    cache_sensing_time,
    get_cached_footprint,
)
from app.services.preview import get_preview


def test_cache_footprint_roundtrip():
    footprint = Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]])
    cache_footprint("product-1", footprint)
    assert get_cached_footprint("product-1") == footprint
    assert get_cached_footprint("unknown-id") is None


async def test_get_preview_returns_relative_image_url_and_bounds():
    footprint = Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]])
    cache_footprint("product-2", footprint)

    result = await get_preview("product-2")

    assert result.productId == "product-2"
    assert result.tileUrl == "/api/preview-image/product-2"
    assert result.bounds == [[4.0, 95.0], [6.0, 98.0]]


async def test_get_preview_raises_for_unknown_product():
    with pytest.raises(ValueError, match="No cached footprint"):
        await get_preview("never-searched")


def test_preview_endpoint_returns_200_for_cached_product(client):
    cache_footprint(
        "router-product-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]]),
    )
    response = client.get("/api/preview/router-product-1")
    assert response.status_code == 200
    body = response.json()
    assert body["productId"] == "router-product-1"
    assert body["tileUrl"] == "/api/preview-image/router-product-1"


def test_preview_endpoint_returns_404_for_unknown_product(client):
    response = client.get("/api/preview/totally-unknown-id")
    assert response.status_code == 404


def test_preview_endpoint_rejects_slc_upfront(client):
    # Consistent UX: the metadata endpoint itself rejects unsupported types,
    # rather than only failing once the browser tries to load the image.
    cache_footprint(
        "slc-metadata-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]]),
    )
    cache_product_type("slc-metadata-1", ProductType.SLC)

    response = client.get("/api/preview/slc-metadata-1")

    assert response.status_code == 404
    assert "GRD" in response.json()["detail"]


def test_preview_endpoint_accepts_sentinel3_lst(client):
    cache_footprint(
        "s3-lst-metadata-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]]),
    )
    cache_product_type("s3-lst-metadata-1", ProductType.S3_SLSTR_L2_LST)

    response = client.get("/api/preview/s3-lst-metadata-1")

    assert response.status_code == 200
    assert response.json()["tileUrl"] == "/api/preview-image/s3-lst-metadata-1"


def test_preview_endpoint_rejects_sentinel3_wst_upfront(client):
    cache_footprint(
        "s3-wst-metadata-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]]),
    )
    cache_product_type("s3-wst-metadata-1", ProductType.S3_SLSTR_L2_WST)

    response = client.get("/api/preview/s3-wst-metadata-1")

    assert response.status_code == 404
    assert "WST" in response.json()["detail"]


@respx.mock
def test_preview_image_endpoint_returns_png_for_grd(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.post("https://wms.test/process").mock(
        return_value=httpx.Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
    )
    cache_footprint(
        "grd-router-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]]),
    )
    cache_sensing_time("grd-router-1", "2026-01-26T11:43:01.722106Z")
    cache_product_type("grd-router-1", ProductType.GRD)

    response = client.get("/api/preview-image/grd-router-1")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"fake-png-bytes"


def test_preview_image_endpoint_returns_404_when_not_cached(client):
    response = client.get("/api/preview-image/never-searched")
    assert response.status_code == 404


def test_preview_image_endpoint_returns_422_for_slc(client):
    cache_footprint(
        "slc-router-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]]),
    )
    cache_sensing_time("slc-router-1", "2026-01-26T11:43:01.722106Z")
    cache_product_type("slc-router-1", ProductType.SLC)

    response = client.get("/api/preview-image/slc-router-1")

    assert response.status_code == 422
    assert "GRD" in response.json()["detail"]


@respx.mock
def test_preview_image_endpoint_returns_jpeg_for_sentinel3_lst(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    cache_footprint(
        "s3-lst-router-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]]),
    )
    cache_product_type("s3-lst-router-1", ProductType.S3_SLSTR_L2_LST)
    cache_quicklook_asset_id("s3-lst-router-1", "asset-xyz")
    respx.get("https://catalogue.test/Assets(asset-xyz)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Assets(asset-xyz)/$value"}
        )
    )
    respx.get("https://download.test/Assets(asset-xyz)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-jpeg-bytes")
    )

    response = client.get("/api/preview-image/s3-lst-router-1")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"fake-jpeg-bytes"


def test_preview_image_endpoint_returns_422_for_sentinel3_wst(client):
    cache_footprint(
        "s3-wst-router-1",
        Footprint(coordinates=[[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0]]]),
    )
    cache_product_type("s3-wst-router-1", ProductType.S3_SLSTR_L2_WST)

    response = client.get("/api/preview-image/s3-wst-router-1")

    assert response.status_code == 422
    assert "WST" in response.json()["detail"]
