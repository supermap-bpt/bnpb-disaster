import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.auth import DownloadTokenManager, get_download_token_manager
from app.config import Settings, get_settings
from app.services.activity_log import activity_log
from app.services.cache import get_cached_product_name, get_cached_product_size
from app.services.download import open_download_stream, should_report_progress as _should_report_progress

router = APIRouter()


def _get_download_token_manager(
    settings: Settings = Depends(get_settings),
) -> DownloadTokenManager:
    return get_download_token_manager(settings)


@router.get(
    "/api/download/{productId}",
    tags=["Download"],
    summary="Download the original product file",
    description=(
        "Streams the original Sentinel-1 .SAFE.zip product from CDSE, proxied through "
        "the backend so the OAuth2 token never reaches the browser."
    ),
)
async def download(
    productId: str,
    settings: Settings = Depends(get_settings),
    token_manager: DownloadTokenManager = Depends(_get_download_token_manager),
) -> StreamingResponse:
    try:
        client, upstream = await open_download_stream(productId, settings, token_manager)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Download upstream error") from exc

    name = get_cached_product_name(productId) or productId
    size = get_cached_product_size(productId)
    description = f"Downloading {name}.zip" + (f" ({size})" if size else "")
    content_length_header = upstream.headers.get("content-length")
    total_bytes = int(content_length_header) if content_length_header else None

    async def iterator():
        async with activity_log(
            action="Download Product",
            category="Satellite",
            description=description,
        ) as log:
            bytes_streamed = 0
            last_reported_pct = -1
            try:
                async for chunk in upstream.aiter_bytes():
                    bytes_streamed += len(chunk)
                    if total_bytes:
                        pct = min(int(bytes_streamed / total_bytes * 100), 100)
                        if _should_report_progress(pct, last_reported_pct):
                            await log.set_progress(pct, f"Downloaded {bytes_streamed} of {total_bytes} bytes")
                            last_reported_pct = pct
                    yield chunk
                # Byte-progress messages above overwrite `description`; restore the
                # size-bearing description as the final one shown once streaming completes.
                await log.set_progress(100, description)
            finally:
                await upstream.aclose()
                await client.aclose()

    return StreamingResponse(
        iterator(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )
