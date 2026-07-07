from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import TokenManager, get_token_manager
from app.config import Settings, get_settings
from app.models import ProductType, SearchQuery, SearchResponse

router = APIRouter()


def _get_token_manager(settings: Settings = Depends(get_settings)) -> TokenManager:
    return get_token_manager(settings)


@router.get(
    "/api/search",
    response_model=SearchResponse,
    tags=["Search"],
    summary="Search Sentinel-1 SAR products",
    description=(
        "Searches the CDSE Catalogue for Sentinel-1 SLC/GRD products matching the given "
        "product type(s), date range, and AOI polygon (viewport or place, frontend's choice)."
    ),
)
async def search(
    # FastAPI does not auto-explode list-typed fields when a Pydantic model is
    # used directly as `Depends()` (it treats them as a request body instead),
    # so productType is declared explicitly here and the model is built by hand.
    productType: list[ProductType] = Query(..., min_length=1),
    dateFrom: date = Query(...),
    dateUntil: date = Query(...),
    aoi: str = Query(..., description="Flat 'lon,lat,lon,lat,...' AOI polygon ring."),
    cloudCoverMax: int = Query(100, ge=0, le=100, description="Max cloud cover %, Sentinel-2 only."),
    skip: int = Query(0, ge=0, description="Pagination offset, for Load More."),
    settings: Settings = Depends(get_settings),
    token_manager: TokenManager = Depends(_get_token_manager),
) -> SearchResponse:
    from app.services.catalogue import search_products

    query = SearchQuery(
        productType=productType,
        dateFrom=dateFrom,
        dateUntil=dateUntil,
        aoi=aoi,
        cloudCoverMax=cloudCoverMax,
        skip=skip,
    )
    try:
        return await search_products(query, settings, token_manager)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Catalogue upstream error") from exc
