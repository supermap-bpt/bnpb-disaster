import httpx
import pytest
import respx

from app.auth import TokenManager
from app.config import Settings
from app.models import ProductType
from app.services.cache import cache_quicklook_asset_id
from app.services.quicklook import fetch_quicklook_image, has_quicklook, unsupported_preview_message


@pytest.fixture
def settings() -> Settings:
    return Settings(
        cdse_identity_url="https://identity.test/token",
        cdse_catalogue_url="https://catalogue.test/Products",
    )


def test_has_quicklook_true_only_for_sentinel3_lst():
    assert has_quicklook(ProductType.S3_SLSTR_L2_LST) is True
    assert has_quicklook(ProductType.S3_SLSTR_L2_WST) is False
    assert has_quicklook(ProductType.GRD) is False
    assert has_quicklook(ProductType.SLC) is False
    assert has_quicklook(ProductType.S2_L2A) is False
    assert has_quicklook(ProductType.S2_L1C) is False


def test_unsupported_preview_message_mentions_grd_and_wst():
    message = unsupported_preview_message(ProductType.S3_SLSTR_L2_WST)
    assert "GRD" in message
    assert "WST" in message


async def test_fetch_quicklook_image_raises_when_no_asset_cached(settings):
    token_manager = TokenManager(settings)
    with pytest.raises(ValueError, match="No quicklook"):
        await fetch_quicklook_image("never-cached-quicklook-product", settings, token_manager)


@respx.mock
async def test_fetch_quicklook_image_follows_redirect_and_returns_bytes(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    cache_quicklook_asset_id("quicklook-product-1", "asset-abc")
    respx.get("https://catalogue.test/Assets(asset-abc)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Assets(asset-abc)/$value"}
        )
    )
    respx.get("https://download.test/Assets(asset-abc)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-jpeg-bytes")
    )
    token_manager = TokenManager(settings)

    result = await fetch_quicklook_image("quicklook-product-1", settings, token_manager)

    assert result == b"fake-jpeg-bytes"
