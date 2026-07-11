from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import TokenManager, get_token_manager
from app.config import Settings, get_settings
from app.models import DemnasFootprintsResponse, ProductType, SearchQuery, SearchResponse

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
    from app.services.demnas import search_demnas

    query = SearchQuery(
        productType=productType,
        dateFrom=dateFrom,
        dateUntil=dateUntil,
        aoi=aoi,
        cloudCoverMax=cloudCoverMax,
        skip=skip,
    )
    demnas_types = {ProductType.DEMNAS_25K, ProductType.DEMNAS_50K}
    try:
        if any(pt in demnas_types for pt in query.productType):
            return await search_demnas(query, settings)
        return await search_products(query, settings, token_manager)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Catalogue upstream error") from exc


@router.get(
    "/api/search/demnas-footprints",
    response_model=DemnasFootprintsResponse,
    tags=["Search"],
    summary="List every matching DEMNAS tile's footprint, unpaginated",
    description=(
        "Every DEMNAS tile matching the given product type(s) and AOI, with no "
        "pagination - so the map can draw the full coverage grid (like BIG's own "
        "DEMNAS portal) while /api/search's result list stays paginated. Lean "
        "payload (id/productType/footprint only, no name/sensingTime/size/etc.)."
    ),
)
async def demnas_footprints(
    productType: list[ProductType] = Query(..., min_length=1),
    aoi: str = Query(..., description="Flat 'lon,lat,lon,lat,...' AOI polygon ring."),
    settings: Settings = Depends(get_settings),
) -> DemnasFootprintsResponse:
    from app.services.demnas import list_demnas_footprints

    return await list_demnas_footprints(productType, aoi, settings)
