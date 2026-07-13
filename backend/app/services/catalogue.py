import re

import httpx

from app.auth import TokenManager
from app.config import Settings
from app.models import Footprint, ProductType, SearchQuery, SearchResponse, SearchResultItem
from app.services.cache import (
    cache_attributes,
    cache_footprint,
    cache_product_name,
    cache_product_size,
    cache_product_type,
    cache_quicklook_asset_id,
    cache_sensing_time,
)

_S1_PRODUCT_TYPE_FILTER = {
    ProductType.SLC: "SLC",
    ProductType.GRD: "GRD",
}
_S2_PRODUCT_TYPE_FILTER = {
    ProductType.S2_L1C: "S2MSI1C",
    ProductType.S2_L2A: "S2MSI2A",
}
# Unlike S1/S2's short markers, CDSE's OData productType filter for Sentinel-3
# requires the exact fixed-width padded value (11 chars, 3 trailing '_'). Removing
# the padding breaks all S3 searches silently (returns 0 results, not an error).
_S3_PRODUCT_TYPE_FILTER = {
    ProductType.S3_SLSTR_L2_LST: "SL_2_LST___",
    ProductType.S3_SLSTR_L2_WST: "SL_2_WST___",
}

# CDSE silently caps results to a small default page (20) when $top is
# omitted. 50 matches Copernicus Browser's observed page size.
SEARCH_PAGE_SIZE = 50


def _product_type_from_raw(raw: str) -> ProductType:
    # CDSE's actual "productType" attribute value is the full product type
    # code (e.g. "IW_GRDH_1S", "IW_SLC__1S", "S2MSI1C", "S2MSI2A"), not the
    # short filter marker - the short form only works as a filter value, not
    # as the value returned in the attribute itself, so matching is by substring.
    for enum, marker in {**_S1_PRODUCT_TYPE_FILTER, **_S2_PRODUCT_TYPE_FILTER, **_S3_PRODUCT_TYPE_FILTER}.items():
        if marker in raw:
            return enum
    raise ValueError(f"Unrecognized productType attribute value: {raw!r}")


def _aoi_to_polygon_wkt(aoi: str) -> str:
    """aoi is a flat 'lon,lat,lon,lat,...' string - either the simplified
    administrative-boundary ring or the place's bounding-box rectangle (both
    built client-side from the geocoded place, never from the map viewport)."""
    values = [float(part) for part in aoi.split(",")]
    points = list(zip(values[0::2], values[1::2]))
    if points[0] != points[-1]:
        points.append(points[0])
    ring = ",".join(f"{lon} {lat}" for lon, lat in points)
    return f"POLYGON(({ring}))"


_S1_INSTRUMENT_CLAUSE = (
    "Attributes/OData.CSC.StringAttribute/any("
    "att:att/Name eq 'instrumentShortName' and att/OData.CSC.StringAttribute/Value eq 'SAR')"
)
_S2_INSTRUMENT_CLAUSE = (
    "Attributes/OData.CSC.StringAttribute/any("
    "att:att/Name eq 'instrumentShortName' and att/OData.CSC.StringAttribute/Value eq 'MSI')"
)
_S3_INSTRUMENT_CLAUSE = (
    "Attributes/OData.CSC.StringAttribute/any("
    "att:att/Name eq 'instrumentShortName' and att/OData.CSC.StringAttribute/Value eq 'SLSTR')"
)


def _type_clause(raw_values: list[str], intersects_clause: str) -> str:
    # CDSE's OData server does not correctly evaluate an OR of Value comparisons
    # inside a single any() lambda (silently returns zero matches even when
    # matching products exist) - each product type needs its own any() call.
    # Intersects is repeated per type-branch (rather than AND'd once at the
    # top level) to mirror the structure observed from Copernicus Browser;
    # logically equivalent either way (distributive AND/OR), kept this way
    # for direct comparability with their captured requests.
    return " or ".join(
        f"(Attributes/OData.CSC.StringAttribute/any("
        f"att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq '{value}') "
        f"and {intersects_clause})"
        for value in raw_values
    )


def build_odata_filter(query: SearchQuery) -> str:
    polygon = _aoi_to_polygon_wkt(query.aoi)
    intersects_clause = f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon}')"
    date_clause = (
        f"ContentDate/Start ge {query.dateFrom}T00:00:00.000Z "
        f"and ContentDate/Start lt {query.dateUntil}T23:59:59.999Z"
    )

    s1_types = [pt for pt in query.productType if pt in _S1_PRODUCT_TYPE_FILTER]
    s2_types = [pt for pt in query.productType if pt in _S2_PRODUCT_TYPE_FILTER]
    s3_types = [pt for pt in query.productType if pt in _S3_PRODUCT_TYPE_FILTER]

    branches: list[str] = []
    if s1_types:
        raw_values = [_S1_PRODUCT_TYPE_FILTER[pt] for pt in s1_types]
        branches.append(
            "(Collection/Name eq 'SENTINEL-1' "
            f"and {date_clause} "
            "and Online eq true "
            f"and {_S1_INSTRUMENT_CLAUSE} "
            f"and ({_type_clause(raw_values, intersects_clause)}))"
        )
    if s2_types:
        raw_values = [_S2_PRODUCT_TYPE_FILTER[pt] for pt in s2_types]
        cloud_clause = (
            "Attributes/OData.CSC.DoubleAttribute/any("
            f"att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {query.cloudCoverMax})"
        )
        branches.append(
            "(Collection/Name eq 'SENTINEL-2' "
            f"and {date_clause} "
            "and Online eq true "
            f"and {_S2_INSTRUMENT_CLAUSE} "
            f"and ({_type_clause(raw_values, intersects_clause)}) "
            f"and {cloud_clause})"
        )
    if s3_types:
        raw_values = [_S3_PRODUCT_TYPE_FILTER[pt] for pt in s3_types]
        branches.append(
            "(Collection/Name eq 'SENTINEL-3' "
            f"and {date_clause} "
            "and Online eq true "
            f"and {_S3_INSTRUMENT_CLAUSE} "
            f"and ({_type_clause(raw_values, intersects_clause)}))"
        )

    return " or ".join(branches)


def _extract_wkt_rings(wkt: str) -> list[list[list[float]]]:
    # Finds every leaf coordinate ring "(...)" regardless of nesting depth -
    # works for POLYGON's single ring and for MULTIPOLYGON's per-polygon ring
    # alike (these footprints never have holes, so every leaf group found
    # this way is an exterior ring, never an inner hole).
    rings_raw = re.findall(r"\(([^()]+)\)", wkt)
    if not rings_raw:
        raise ValueError(f"Unsupported footprint WKT: {wkt}")
    return [
        [[float(x), float(y)] for x, y in (pair.split() for pair in ring.split(","))]
        for ring in rings_raw
    ]


def parse_wkt_polygon(wkt: str) -> list[list[list[float]]]:
    return [_extract_wkt_rings(wkt)[0]]


def parse_wkt_footprint(wkt: str) -> tuple[str, list]:
    # CDSE returns MULTIPOLYGON (rather than POLYGON) for footprints that
    # cross the antimeridian - observed for Sentinel-3 WST's near-global,
    # near-polar swaths. Splitting on that gives the correct GeoJSON shape
    # for either case: Polygon -> [ring]; MultiPolygon -> [[ring], [ring], ...].
    rings = _extract_wkt_rings(wkt)
    if "MULTIPOLYGON" in wkt.upper():
        return "MultiPolygon", [[ring] for ring in rings]
    return "Polygon", [rings[0]]


def _attr_value(attributes: list[dict], name: str, default: str = "") -> str:
    for attr in attributes:
        if attr.get("Name") == name:
            return attr.get("Value", default)
    return default


def _to_human_size(content_length: int) -> str:
    megabytes = content_length / (1024 * 1024)
    return f"{megabytes:.0f}MB"


def _cloud_cover_from_attributes(attributes: list[dict]) -> float | None:
    raw = _attr_value(attributes, "cloudCover", "")
    return None if raw == "" else float(raw)


async def search_products(
    query: SearchQuery, settings: Settings, token_manager: TokenManager
) -> SearchResponse:
    token = await token_manager.get_token()
    odata_filter = build_odata_filter(query)

    timeout = httpx.Timeout(
        connect=30.0,
        read=180.0,
        write=30.0,
        pool=30.0,
    )

    params = {
        "$filter": odata_filter,
        # Must be a LIST, not "Attributes,Assets": CDSE rejects a comma-joined
        # $expand with HTTP 400 ("Expand parameter only accepts following
        # values..."). httpx serializes a list as repeated $expand=... params,
        # which is the form CDSE's OData actually requires - verified live.
        # Collapsing this back to a single string breaks every search.
        "$expand": ["Attributes", "Assets"],
        "$top": SEARCH_PAGE_SIZE,
        "$skip": query.skip,
        "$count": "true",
        "$orderby": "ContentDate/Start desc",
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    print("\n========== CDSE SEARCH ==========")
    print("Catalogue URL :", settings.cdse_catalogue_url)
    print("Skip          :", query.skip)
    print("Top           :", SEARCH_PAGE_SIZE)
    print("AOI           :", query.aoi)
    print("Date From     :", query.dateFrom)
    print("Date Until    :", query.dateUntil)
    print("Cloud Cover   :", query.cloudCoverMax)
    print("Filter:")
    print(odata_filter)
    print("=================================\n")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:

            request = client.build_request(
                "GET",
                settings.cdse_catalogue_url,
                params=params,
                headers=headers,
            )

            print("Request URL:")
            print(request.url)

            response = await client.send(request)

            response.raise_for_status()

            payload = response.json()

    except httpx.ReadTimeout as exc:
        raise RuntimeError(
            "Copernicus Catalogue request timed out after 180 seconds."
        ) from exc

    except httpx.HTTPStatusError as exc:
        print("CDSE Response:")
        print(exc.response.text)

        raise RuntimeError(
            f"Copernicus Catalogue returned HTTP {exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Network error while connecting to Copernicus Catalogue: {exc}"
        ) from exc

    items: list[SearchResultItem] = []

    for entry in payload.get("value", []):

        attributes = entry.get("Attributes", [])

        raw_product_type = _attr_value(attributes, "productType")
        footprint_type, footprint_coordinates = parse_wkt_footprint(entry["Footprint"])

        item = SearchResultItem(
            id=entry["Id"],
            name=entry["Name"],
            productType=_product_type_from_raw(raw_product_type),
            sensingTime=entry["ContentDate"]["Start"],
            size=_to_human_size(entry["ContentLength"]),
            polarisation=_attr_value(attributes, "polarisationChannels", "N/A"),
            cloudCoverPercentage=_cloud_cover_from_attributes(attributes),
            footprint=Footprint(type=footprint_type, coordinates=footprint_coordinates),
        )

        cache_footprint(item.id, item.footprint)
        cache_product_name(item.id, item.name)
        cache_product_size(item.id, item.size)
        cache_sensing_time(item.id, item.sensingTime)
        cache_product_type(item.id, item.productType)
        cache_attributes(item.id, attributes)

        quicklook_asset = next(
            (asset for asset in entry.get("Assets", []) if asset.get("Type") == "QUICKLOOK"),
            None,
        )
        if quicklook_asset is not None:
            cache_quicklook_asset_id(item.id, quicklook_asset["Id"])

        items.append(item)

    total = payload.get("@odata.count", len(items))

    print(f"Found {total} products")
    print(f"Returned {len(items)} products")

    return SearchResponse(
        results=items,
        total=total,
    )
