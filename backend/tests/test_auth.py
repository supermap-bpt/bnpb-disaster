import time

import httpx
import pytest
import respx

from app.auth import DownloadTokenManager, TokenManager
from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        cdse_client_id="test-id",
        cdse_client_secret="test-secret",
        cdse_username="test-user@example.com",
        cdse_password="test-password",
        cdse_identity_url="https://identity.test/token",
    )


@respx.mock
async def test_get_token_fetches_and_caches(settings):
    route = respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    manager = TokenManager(settings)

    token1 = await manager.get_token()
    token2 = await manager.get_token()

    assert token1 == "tok-1"
    assert token2 == "tok-1"
    assert route.call_count == 1


@respx.mock
async def test_get_token_refreshes_after_expiry(settings):
    route = respx.post("https://identity.test/token").mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "tok-1", "expires_in": 1}),
            httpx.Response(200, json={"access_token": "tok-2", "expires_in": 600}),
        ]
    )
    manager = TokenManager(settings)

    token1 = await manager.get_token()
    time.sleep(1.1)
    token2 = await manager.get_token()

    assert token1 == "tok-1"
    assert token2 == "tok-2"
    assert route.call_count == 2


@respx.mock
async def test_download_token_manager_uses_password_grant_against_cdse_public(settings):
    route = respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "dl-tok-1", "expires_in": 600})
    )
    manager = DownloadTokenManager(settings)

    token = await manager.get_token()

    assert token == "dl-tok-1"
    sent_body = route.calls.last.request.content.decode()
    assert "grant_type=password" in sent_body
    assert "client_id=cdse-public" in sent_body
    assert "username=test-user%40example.com" in sent_body
