import httpx

from app.config import Settings
from app.models import Footprint, ProductType, SearchQuery, SearchResponse, SearchResultItem
from app.services.cache import (
    cache_attributes,
    cache_footprint,
    cache_product_name,
    cache_product_size,
    cache_product_type,
    cache_sensing_time,
)
from app.services.catalogue import SEARCH_PAGE_SIZE

_SKALA_TO_PRODUCT_TYPE = {
    "25K": ProductType.DEMNAS_25K,
    "50K": ProductType.DEMNAS_50K,
}

# Tried in order; first non-null wins. The source data uses different year
# fields depending on which regional layer a tile came from - some values
# have a stray trailing underscore observed in the wild (e.g. "2006_").
_YEAR_FIELDS = ("Tahun", "THN_DTM", "TAHUN_BUAT", "THN_UPDATE")
# Year 1 is unambiguously not a real acquisition year, while still being a
# valid parseable datetime for the Save-Satellite flow's required field.
_UNKNOWN_YEAR_SENTINEL = "0001-01-01T00:00:00Z"

_demnas_cache: dict | None = None


async def _load_demnas(settings: Settings) -> dict:
    global _demnas_cache
    if _demnas_cache is None:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(settings.demnas_url)
            response.raise_for_status()
            _demnas_cache = response.json()
    return _demnas_cache


def _aoi_bbox(aoi: str) -> tuple[float, float, float, float]:
    values = [float(part) for part in aoi.split(",")]
    lons = values[0::2]
    lats = values[1::2]
    return min(lons), min(lats), max(lons), max(lats)


def _feature_bbox(coordinates: list) -> tuple[float, float, float, float]:
    lons = [point[0] for ring in coordinates for point in ring]
    lats = [point[1] for ring in coordinates for point in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _bboxes_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    a_min_lon, a_min_lat, a_max_lon, a_max_lat = a
    b_min_lon, b_min_lat, b_max_lon, b_max_lat = b
    return (
        a_min_lon <= b_max_lon
        and a_max_lon >= b_min_lon
        and a_min_lat <= b_max_lat
        and a_max_lat >= b_min_lat
    )


def _sensing_time_from_properties(properties: dict) -> str:
    for field in _YEAR_FIELDS:
        value = properties.get(field)
        if not value:
            continue
        year = str(value).strip().rstrip("_")
        if year.isdigit():
            return f"{year}-01-01T00:00:00Z"
    return _UNKNOWN_YEAR_SENTINEL


def _drop_z(ring: list[list[float]]) -> list[list[float]]:
    return [[point[0], point[1]] for point in ring]


def _feature_to_item(feature: dict, index: int) -> SearchResultItem | None:
    properties = feature.get("properties", {})
    product_type = _SKALA_TO_PRODUCT_TYPE.get(properties.get("SKALA"))
    if product_type is None:
        return None

    ring = _drop_z(feature["geometry"]["coordinates"][0])
    item_id = properties.get("NAMOBJ") or properties.get("NAME_FILE") or f"demnas-{index}"
    name = properties.get("NAME_FILE") or properties.get("NAMOBJ") or item_id

    return SearchResultItem(
        id=item_id,
        name=name,
        productType=product_type,
        sensingTime=_sensing_time_from_properties(properties),
        size="N/A",
        polarisation="N/A",
        cloudCoverPercentage=None,
        footprint=Footprint(type="Polygon", coordinates=[ring]),
    )


async def search_demnas(query: SearchQuery, settings: Settings) -> SearchResponse:
    collection = await _load_demnas(settings)
    aoi_bbox = _aoi_bbox(query.aoi)

    matches: list[tuple[SearchResultItem, dict]] = []
    for index, feature in enumerate(collection.get("features", [])):
        item = _feature_to_item(feature, index)
        if item is None:
            continue
        if item.productType not in query.productType:
            continue
        tile_bbox = _feature_bbox(feature["geometry"]["coordinates"])
        if not _bboxes_overlap(aoi_bbox, tile_bbox):
            continue
        matches.append((item, feature.get("properties", {})))

    total = len(matches)
    page = matches[query.skip : query.skip + SEARCH_PAGE_SIZE]

    results: list[SearchResultItem] = []
    for item, properties in page:
        cache_footprint(item.id, item.footprint)
        cache_product_name(item.id, item.name)
        cache_product_size(item.id, item.size)
        cache_sensing_time(item.id, item.sensingTime)
        cache_product_type(item.id, item.productType)
        cache_attributes(
            item.id,
            [
                {"Name": key, "Value": str(value)}
                for key, value in properties.items()
                if value is not None
            ],
        )
        results.append(item)

    return SearchResponse(results=results, total=total)
