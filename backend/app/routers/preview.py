import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import TokenManager
from app.config import Settings, get_settings
from app.models import PreviewResponse
from app.routers.search import _get_token_manager
from app.services.cache import get_cached_product_type
from app.services.preview import get_preview
from app.services.quicklook import fetch_quicklook_image, has_quicklook, unsupported_preview_message
from app.services.render import is_renderable, render_product_image

router = APIRouter()


@router.get(
    "/api/preview/{productId}",
    response_model=PreviewResponse,
    tags=["Preview"],
    summary="Get imagery preview metadata for a selected product",
    description=(
        "Returns the tile URL (our own /api/preview-image proxy) and bounds for the "
        "imagery of a product previously returned by /api/search. The product must "
        "have been cached by a prior search."
    ),
)
async def preview(productId: str) -> PreviewResponse:
    try:
        return await get_preview(productId)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/api/preview-image/{productId}",
    tags=["Preview"],
    summary="Render the actual satellite image for a product",
    description=(
        "Server-side proxy to the Sentinel Hub Process API: renders the exact "
        "selected acquisition's SAR backscatter as a PNG, scoped to its cached "
        "footprint and sensing date - never a default/latest/nearest scene. "
        "GRD only: Sentinel-1 SLC is not a Process API collection."
    ),
)
async def preview_image(
    productId: str,
    settings: Settings = Depends(get_settings),
    token_manager: TokenManager = Depends(_get_token_manager),
) -> Response:
    product_type = get_cached_product_type(productId)
    if product_type is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached data for product {productId}. Run a search first.",
        )
    try:
        if is_renderable(product_type):
            image_bytes = await render_product_image(productId, product_type, settings, token_manager)
            return Response(content=image_bytes, media_type="image/png")
        if has_quicklook(product_type):
            image_bytes = await fetch_quicklook_image(productId, settings, token_manager)
            return Response(content=image_bytes, media_type="image/jpeg")
        raise ValueError(unsupported_preview_message(product_type))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Render upstream error") from exc
