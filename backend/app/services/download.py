import httpx

from app.auth import DownloadTokenManager
from app.config import Settings


def should_report_progress(current_pct: int, last_reported_pct: int) -> bool:
    return current_pct >= last_reported_pct + 5 or current_pct == 100


async def open_download_stream(
    product_id: str, settings: Settings, token_manager: DownloadTokenManager
) -> tuple[httpx.AsyncClient, httpx.Response]:
    token = await token_manager.get_token()
    url = f"{settings.cdse_catalogue_url}({product_id})/$value"
    client = httpx.AsyncClient(timeout=None)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        request = client.build_request("GET", url, headers=headers)
        response = await client.send(request, stream=True)

        # CDSE redirects $value to a different host (download.dataspace.copernicus.eu).
        # httpx does not auto-follow redirects by default, and even if it did it would
        # drop the Authorization header across hosts - so the redirect is followed
        # manually here, re-attaching the same token.
        if response.is_redirect:
            redirect_url = response.headers["location"]
            await response.aclose()
            request = client.build_request("GET", redirect_url, headers=headers)
            response = await client.send(request, stream=True)

        if response.status_code != 200:
            await response.aclose()
            raise httpx.HTTPStatusError(
                f"Download upstream returned {response.status_code}",
                request=request,
                response=response,
            )
    except Exception:
        # Whether client.send() itself raised (e.g. ConnectError, ReadTimeout) or a
        # non-200 response was turned into HTTPStatusError above, the AsyncClient
        # must not be leaked - close it before propagating.
        await client.aclose()
        raise
    return client, response
