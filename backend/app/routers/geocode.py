import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import Settings, get_settings
from app.models import GeocodeSuggestionsResponse
from app.services.geocode import geocode_suggestions

router = APIRouter()


@router.get(
    "/api/geocode",
    response_model=GeocodeSuggestionsResponse,
    tags=["Geocoding"],
    summary="Geocode an address to a list of candidate locations",
    description=(
        "Proxies OpenStreetMap Nominatim to convert a free-text address into a list of "
        "candidate lat/lng suggestions, for live search-as-you-type address lookup."
    ),
)
async def geocode(
    q: str = Query(..., min_length=1, description="Free-text address to geocode."),
    limit: int = Query(5, ge=1, le=10, description="Max number of suggestions to return."),
    settings: Settings = Depends(get_settings),
) -> GeocodeSuggestionsResponse:
    try:
        results = await geocode_suggestions(q, settings, limit)
        return GeocodeSuggestionsResponse(results=results)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Geocoding upstream error") from exc
