import httpx

from app.config import Settings
from app.models import GeocodeResponse
from app.services.geometry import simplify_ring_to_max_points


def _parse_bbox(raw_boundingbox: list[str]) -> list[float]:
    # Nominatim order is [south, north, west, east] - normalize to this app's
    # convention used everywhere else: [minLon, minLat, maxLon, maxLat].
    south, north, west, east = (float(v) for v in raw_boundingbox)
    return [west, south, east, north]


def _parse_polygon(geojson: dict | None) -> list[list[float]] | None:
    if geojson is None:
        return None

    if geojson["type"] == "Polygon":
        ring = geojson["coordinates"][0]
    elif geojson["type"] == "MultiPolygon":
        # Heuristic: use the most detailed part (most vertices) as a stand-in for
        # "largest" - exact area-based selection isn't worth the complexity here.
        ring = max((part[0] for part in geojson["coordinates"]), key=len)
    else:
        return None

    return simplify_ring_to_max_points(ring, max_points=150)


async def geocode_suggestions(
    query: str, settings: Settings, limit: int = 5
) -> list[GeocodeResponse]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.nominatim_url,
            params={"q": query, "format": "json", "limit": limit, "polygon_geojson": 1},
            headers={"User-Agent": "sentinel1-sar-browser/1.0"},
        )
        response.raise_for_status()
        results = response.json()

    return [
        GeocodeResponse(
            lat=float(item["lat"]),
            lng=float(item["lon"]),
            displayName=item["display_name"],
            bbox=_parse_bbox(item["boundingbox"]),
            polygon=_parse_polygon(item.get("geojson")),
        )
        for item in results
    ]
