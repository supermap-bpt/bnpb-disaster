import time

import httpx

from app.config import Settings


class _CachedTokenManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._expires_at: float = 0.0

    def _grant_data(self) -> dict[str, str]:
        raise NotImplementedError

    async def get_token(self) -> str:
        if self._token is not None and time.monotonic() < self._expires_at:
            return self._token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._settings.cdse_identity_url,
                data=self._grant_data(),
            )
            response.raise_for_status()
            payload = response.json()

        self._token = payload["access_token"]
        self._expires_at = time.monotonic() + max(payload["expires_in"] - 5, 0)
        return self._token


class TokenManager(_CachedTokenManager):
    """client_credentials grant - used for Catalogue search/preview, scoped to the
    Sentinel Hub OAuth client."""

    def _grant_data(self) -> dict[str, str]:
        return {
            "grant_type": "client_credentials",
            "client_id": self._settings.cdse_client_id,
            "client_secret": self._settings.cdse_client_secret,
        }


class DownloadTokenManager(_CachedTokenManager):
    """password grant against the public "cdse-public" client - the only audience
    CDSE's download/zipper service ($value) accepts; client_credentials tokens are
    rejected with "Token audience not allowed"."""

    def _grant_data(self) -> dict[str, str]:
        return {
            "grant_type": "password",
            "client_id": "cdse-public",
            "username": self._settings.cdse_username,
            "password": self._settings.cdse_password,
        }


_managers: dict[int, TokenManager] = {}
_download_managers: dict[int, DownloadTokenManager] = {}


def get_token_manager(settings: Settings) -> TokenManager:
    key = id(settings)
    if key not in _managers:
        _managers[key] = TokenManager(settings)
    return _managers[key]


def get_download_token_manager(settings: Settings) -> DownloadTokenManager:
    key = id(settings)
    if key not in _download_managers:
        _download_managers[key] = DownloadTokenManager(settings)
    return _download_managers[key]
