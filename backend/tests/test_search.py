import httpx
import pytest
import respx

from app.auth import TokenManager
from app.config import Settings
from app.models import ProductType, SearchQuery
from app.services.cache import get_cached_attributes, get_cached_product_size, get_cached_quicklook_asset_id
from app.services.catalogue import (
    _aoi_to_polygon_wkt,
    build_odata_filter,
    parse_wkt_footprint,
    parse_wkt_polygon,
    search_products,
)


def test_parse_wkt_polygon_extracts_coordinate_pairs():
    wkt = "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, 98.0 6.0, 95.0 6.0, 95.0 4.0))'"
    coords = parse_wkt_polygon(wkt)
    assert coords == [[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0], [95.0, 4.0]]]


def test_parse_wkt_footprint_returns_polygon_type_for_a_plain_polygon():
    wkt = "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, 98.0 6.0, 95.0 6.0, 95.0 4.0))'"
    geometry_type, coordinates = parse_wkt_footprint(wkt)
    assert geometry_type == "Polygon"
    assert coordinates == [[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0], [95.0, 6.0], [95.0, 4.0]]]


def test_parse_wkt_footprint_returns_multipolygon_type_for_antimeridian_crossing_footprint():
    # Real shape CDSE returns for footprints crossing the antimeridian (e.g.
    # Sentinel-3 WST's near-global, near-polar swaths) - two separate rings,
    # one either side of the 180th meridian.
    wkt = (
        "geography'SRID=4326;MULTIPOLYGON ("
        "((180 -83.1, 180 -61.6, 172.7 -81.7, 180 -83.1)), "
        "((-180 -61.6, -180 -83.1, -179.4 -83.2, -180 -61.6)))'"
    )
    geometry_type, coordinates = parse_wkt_footprint(wkt)
    assert geometry_type == "MultiPolygon"
    assert coordinates == [
        [[[180.0, -83.1], [180.0, -61.6], [172.7, -81.7], [180.0, -83.1]]],
        [[[-180.0, -61.6], [-180.0, -83.1], [-179.4, -83.2], [-180.0, -61.6]]],
    ]


def test_aoi_to_polygon_wkt_builds_closed_rectangle_from_bbox_corners():
    wkt = _aoi_to_polygon_wkt("95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0")
    assert wkt == "POLYGON((95.0 4.0,98.0 4.0,98.0 6.0,95.0 6.0,95.0 4.0))"


def test_aoi_to_polygon_wkt_closes_an_already_open_ring():
    # 3-point triangle, not explicitly closed by the caller.
    wkt = _aoi_to_polygon_wkt("95.0,4.0,98.0,4.0,96.5,6.0")
    assert wkt == "POLYGON((95.0 4.0,98.0 4.0,96.5 6.0,95.0 4.0))"


def test_build_odata_filter_includes_single_product_type_dates_and_aoi():
    query = SearchQuery(
        productType=[ProductType.GRD],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    filter_str = build_odata_filter(query)
    assert "SENTINEL-1" in filter_str
    assert "2026-01-01" in filter_str
    assert "2026-02-01" in filter_str
    assert "GRD" in filter_str
    assert "OData.CSC.Intersects(area=geography'SRID=4326;POLYGON((95.0 4.0" in filter_str
    # ge (inclusive lower) / lt (exclusive upper, day-boundary padded so the
    # whole dateUntil day is still covered in practice).
    assert "ContentDate/Start ge 2026-01-01" in filter_str
    assert "ContentDate/Start lt 2026-02-01" in filter_str
    assert "Online eq true" in filter_str
    assert "instrumentShortName" in filter_str and "SAR" in filter_str


def test_build_odata_filter_ors_multiple_product_types_each_with_its_own_intersects():
    query = SearchQuery(
        productType=[ProductType.SLC, ProductType.GRD],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    filter_str = build_odata_filter(query)
    assert "SLC" in filter_str
    assert "GRD" in filter_str
    assert " or " in filter_str
    # Each product-type branch carries its own Intersects clause, matching
    # the structure Copernicus Browser's captured requests use - logically
    # equivalent to AND-ing Intersects once at the top level, but kept this
    # way for direct comparability.
    assert filter_str.count("OData.CSC.Intersects") == 2


def test_build_odata_filter_handles_non_rectangular_aoi():
    # A real AOI is an arbitrary administrative-boundary ring, not necessarily
    # a 4-corner rectangle - confirm the filter builder doesn't assume one.
    query = SearchQuery(
        productType=[ProductType.GRD],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,96.0,4.5,97.0,4.0,96.5,5.5,95.5,5.0",
    )
    filter_str = build_odata_filter(query)
    assert "POLYGON((95.0 4.0,96.0 4.5,97.0 4.0,96.5 5.5,95.5 5.0,95.0 4.0))" in filter_str


def test_build_odata_filter_builds_sentinel2_branch_with_cloud_cover():
    query = SearchQuery(
        productType=[ProductType.S2_L2A],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        cloudCoverMax=30,
    )
    filter_str = build_odata_filter(query)
    assert "SENTINEL-2" in filter_str
    assert "S2MSI2A" in filter_str
    assert "instrumentShortName" in filter_str and "MSI" in filter_str
    assert "cloudCover" in filter_str and "le 30" in filter_str
    assert "SENTINEL-1" not in filter_str


def test_build_odata_filter_ors_sentinel1_and_sentinel2_branches():
    query = SearchQuery(
        productType=[ProductType.GRD, ProductType.S2_L2A],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        cloudCoverMax=50,
    )
    filter_str = build_odata_filter(query)
    assert "SENTINEL-1" in filter_str
    assert "SENTINEL-2" in filter_str
    assert "GRD" in filter_str
    assert "S2MSI2A" in filter_str
    assert filter_str.count(" or ") >= 1


def test_build_odata_filter_builds_sentinel3_branch_with_no_cloud_cover():
    query = SearchQuery(
        productType=[ProductType.S3_SLSTR_L2_LST, ProductType.S3_SLSTR_L2_WST],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    filter_str = build_odata_filter(query)
    assert "SENTINEL-3" in filter_str
    assert "SL_2_LST___" in filter_str
    assert "SL_2_WST___" in filter_str
    assert "instrumentShortName" in filter_str and "SLSTR" in filter_str
    assert "cloudCover" not in filter_str
    assert "SENTINEL-1" not in filter_str
    assert "SENTINEL-2" not in filter_str


def test_build_odata_filter_ors_sentinel1_and_sentinel3_branches():
    query = SearchQuery(
        productType=[ProductType.GRD, ProductType.S3_SLSTR_L2_LST],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    filter_str = build_odata_filter(query)
    assert "SENTINEL-1" in filter_str
    assert "SENTINEL-3" in filter_str
    assert "GRD" in filter_str
    assert "SL_2_LST___" in filter_str
    assert filter_str.count(" or ") >= 1


@respx.mock
async def test_search_products_parses_cloud_cover_for_sentinel2(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.count": 1,
                "value": [
                    {
                        "Id": "S2A_MSIL2A_20260126T114301",
                        "Name": "S2A_MSIL2A_20260126T114301.SAFE",
                        "ContentDate": {"Start": "2026-01-26T11:43:01.722106Z"},
                        "ContentLength": 734003200,
                        "Footprint": (
                            "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                            "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                        ),
                        "Attributes": [
                            {"Name": "productType", "Value": "S2MSI2A"},
                            {"Name": "cloudCover", "Value": "12.5"},
                        ],
                    },
                ],
            },
        )
    )
    query = SearchQuery(
        productType=[ProductType.S2_L2A],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    token_manager = TokenManager(settings)

    result = await search_products(query, settings, token_manager)

    assert result.results[0].productType is ProductType.S2_L2A
    assert result.results[0].cloudCoverPercentage == 12.5
    assert result.results[0].polarisation == "N/A"


@respx.mock
async def test_search_products_treats_cloud_cover_zero_as_real_value(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.count": 1,
                "value": [
                    {
                        "Id": "S2A_MSIL2A_20260127T114301",
                        "Name": "S2A_MSIL2A_20260127T114301.SAFE",
                        "ContentDate": {"Start": "2026-01-27T11:43:01.722106Z"},
                        "ContentLength": 734003200,
                        "Footprint": (
                            "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                            "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                        ),
                        "Attributes": [
                            {"Name": "productType", "Value": "S2MSI2A"},
                            {"Name": "cloudCover", "Value": "0"},
                        ],
                    },
                ],
            },
        )
    )
    query = SearchQuery(
        productType=[ProductType.S2_L2A],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    token_manager = TokenManager(settings)

    result = await search_products(query, settings, token_manager)

    assert result.results[0].productType is ProductType.S2_L2A
    assert result.results[0].cloudCoverPercentage == 0.0
    assert result.results[0].polarisation == "N/A"


@respx.mock
async def test_search_products_leaves_cloud_cover_none_for_sentinel1(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.count": 1,
                "value": [
                    {
                        "Id": "S1A_IW_GRDH_1SDV_20260126T114301",
                        "Name": "S1A_IW_GRDH_1SDV_20260126T114301.SAFE",
                        "ContentDate": {"Start": "2026-01-26T11:43:01.722106Z"},
                        "ContentLength": 1712336896,
                        "Footprint": (
                            "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                            "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                        ),
                        "Attributes": [
                            {"Name": "productType", "Value": "IW_GRDH_1S"},
                            {"Name": "polarisationChannels", "Value": "VV&VH"},
                        ],
                    },
                ],
            },
        )
    )
    query = SearchQuery(
        productType=[ProductType.GRD],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    token_manager = TokenManager(settings)

    result = await search_products(query, settings, token_manager)

    assert result.results[0].cloudCoverPercentage is None


@respx.mock
async def test_search_products_parses_sentinel3_slstr_lst(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.count": 1,
                "value": [
                    {
                        "Id": "S3A_SL_2_LST____20260126T114301",
                        "Name": "S3A_SL_2_LST____20260126T114301.SEN3",
                        "ContentDate": {"Start": "2026-01-26T11:43:01.722106Z"},
                        "ContentLength": 314572800,
                        "Footprint": (
                            "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                            "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                        ),
                        "Attributes": [
                            {"Name": "productType", "Value": "SL_2_LST___"},
                        ],
                    },
                ],
            },
        )
    )
    query = SearchQuery(
        productType=[ProductType.S3_SLSTR_L2_LST],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    token_manager = TokenManager(settings)

    result = await search_products(query, settings, token_manager)

    assert result.results[0].productType is ProductType.S3_SLSTR_L2_LST
    assert result.results[0].polarisation == "N/A"
    assert result.results[0].cloudCoverPercentage is None


@pytest.fixture
def settings() -> Settings:
    return Settings(
        cdse_identity_url="https://identity.test/token",
        cdse_catalogue_url="https://catalogue.test/Products",
    )


@respx.mock
async def test_search_products_returns_parsed_results_with_type_from_attributes(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    catalogue_route = respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.count": 66,
                "value": [
                    {
                        "Id": "S1A_IW_GRDH_1SDV_20260126T114301",
                        "Name": "S1A_IW_GRDH_1SDV_20260126T114301.SAFE",
                        "ContentDate": {"Start": "2026-01-26T11:43:01.722106Z"},
                        "ContentLength": 1712336896,
                        "Footprint": (
                            "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                            "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                        ),
                        # Real CDSE returns the full product type code here
                        # (e.g. "IW_GRDH_1S"), not the short "GRD"/"SLC" used
                        # to filter - regression test for that mismatch.
                        "Attributes": [
                            {"Name": "productType", "Value": "IW_GRDH_1S"},
                            {"Name": "polarisationChannels", "Value": "VV&VH"},
                        ],
                    },
                    {
                        "Id": "S1A_IW_SLC__1SDV_20260126T114301",
                        "Name": "S1A_IW_SLC__1SDV_20260126T114301.SAFE",
                        "ContentDate": {"Start": "2026-01-26T11:43:01.722106Z"},
                        "ContentLength": 4294967296,
                        "Footprint": (
                            "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                            "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                        ),
                        "Attributes": [
                            {"Name": "productType", "Value": "IW_SLC__1S"},
                            {"Name": "polarisationChannels", "Value": "VV&VH"},
                        ],
                    },
                ]
            },
        )
    )
    query = SearchQuery(
        productType=[ProductType.SLC, ProductType.GRD],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    token_manager = TokenManager(settings)

    result = await search_products(query, settings, token_manager)

    assert len(result.results) == 2
    assert result.total == 66
    assert result.results[0].productType is ProductType.GRD
    assert result.results[0].name == "S1A_IW_GRDH_1SDV_20260126T114301.SAFE"
    assert result.results[1].productType is ProductType.SLC
    assert result.results[0].footprint.coordinates[0][0] == [95.0, 4.0]
    request_url = str(catalogue_route.calls.last.request.url)
    # Regression: without $expand=Attributes, CDSE omits the Attributes field
    # entirely and every product type lookup silently breaks.
    assert "expand=Attributes" in request_url
    # Regression: without $top, CDSE silently caps results to a small default
    # page (20) instead of the actual total - see SEARCH_PAGE_SIZE.
    assert "top=50" in request_url
    assert "skip=0" in request_url
    assert "count=true" in request_url
    assert "orderby=ContentDate%2FStart%20desc" in request_url
    # Regression: the raw Attributes array must be cached per product so the
    # /api/products/{id}/attributes Info endpoint can serve it without a
    # second CDSE round-trip.
    assert get_cached_attributes("S1A_IW_GRDH_1SDV_20260126T114301") == [
        {"Name": "productType", "Value": "IW_GRDH_1S"},
        {"Name": "polarisationChannels", "Value": "VV&VH"},
    ]
    # Regression: size must be cached per product so a later Download Product
    # log entry can show it without a second CDSE round-trip.
    assert get_cached_product_size("S1A_IW_GRDH_1SDV_20260126T114301") == "1633MB"


@respx.mock
async def test_search_products_caches_quicklook_asset_id_when_present(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    catalogue_route = respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.count": 1,
                "value": [
                    {
                        "Id": "S3A_SL_2_LST____20260610T160122",
                        "Name": "S3A_SL_2_LST____20260610T160122.SEN3",
                        "ContentDate": {"Start": "2026-06-10T16:01:22.000000Z"},
                        "ContentLength": 62914560,
                        "Footprint": (
                            "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                            "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                        ),
                        "Attributes": [
                            {"Name": "productType", "Value": "SL_2_LST___"},
                        ],
                        "Assets": [
                            {
                                "Type": "QUICKLOOK",
                                "Id": "asset-quicklook-1",
                                "DownloadLink": "https://catalogue.test/Assets(asset-quicklook-1)/$value",
                            }
                        ],
                    },
                ],
            },
        )
    )
    query = SearchQuery(
        productType=[ProductType.S3_SLSTR_L2_LST],
        dateFrom="2026-06-01",
        dateUntil="2026-06-30",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    token_manager = TokenManager(settings)

    result = await search_products(query, settings, token_manager)

    assert result.results[0].productType is ProductType.S3_SLSTR_L2_LST
    assert get_cached_quicklook_asset_id("S3A_SL_2_LST____20260610T160122") == "asset-quicklook-1"
    request_url = str(catalogue_route.calls.last.request.url)
    assert request_url.count("expand=Attributes") == 1
    assert request_url.count("expand=Assets") == 1


@respx.mock
async def test_search_products_leaves_quicklook_asset_id_uncached_when_assets_empty(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.count": 1,
                "value": [
                    {
                        "Id": "S3A_SL_2_WST____20260610T150712",
                        "Name": "S3A_SL_2_WST____20260610T150712.SEN3",
                        "ContentDate": {"Start": "2026-06-10T15:07:12.000000Z"},
                        "ContentLength": 62914560,
                        "Footprint": (
                            "geography'SRID=4326;POLYGON((95.0 4.0, 98.0 4.0, "
                            "98.0 6.0, 95.0 6.0, 95.0 4.0))'"
                        ),
                        "Attributes": [
                            {"Name": "productType", "Value": "SL_2_WST___"},
                        ],
                        "Assets": [],
                    },
                ],
            },
        )
    )
    query = SearchQuery(
        productType=[ProductType.S3_SLSTR_L2_WST],
        dateFrom="2026-06-01",
        dateUntil="2026-06-30",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    token_manager = TokenManager(settings)

    await search_products(query, settings, token_manager)

    assert get_cached_quicklook_asset_id("S3A_SL_2_WST____20260610T150712") is None


@respx.mock
async def test_search_products_passes_skip_through_for_pagination(settings):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    catalogue_route = respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(200, json={"@odata.count": 66, "value": []})
    )
    query = SearchQuery(
        productType=[ProductType.GRD],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        skip=50,
    )
    token_manager = TokenManager(settings)

    await search_products(query, settings, token_manager)

    request_url = str(catalogue_route.calls.last.request.url)
    assert "skip=50" in request_url


@respx.mock
def test_search_endpoint_accepts_multiple_product_types(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    response = client.get(
        "/api/search",
        params={
            "productType": ["SENTINEL_1_SLC", "SENTINEL_1_GRD"],
            "dateFrom": "2026-01-01",
            "dateUntil": "2026-02-01",
            "aoi": "95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"results": [], "total": 0}


def test_search_endpoint_rejects_missing_product_type(client):
    response = client.get(
        "/api/search",
        params={
            "dateFrom": "2026-01-01",
            "dateUntil": "2026-02-01",
            "aoi": "95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        },
    )
    assert response.status_code == 422


def test_search_endpoint_rejects_invalid_date_range(client):
    response = client.get(
        "/api/search",
        params={
            "productType": ["SENTINEL_1_GRD"],
            "dateFrom": "2026-02-01",
            "dateUntil": "2026-01-01",
            "aoi": "95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        },
    )
    assert response.status_code == 422


def test_search_endpoint_rejects_cloud_cover_max_above_100(client):
    response = client.get(
        "/api/search",
        params={
            "productType": ["SENTINEL_2_L2A"],
            "dateFrom": "2026-01-01",
            "dateUntil": "2026-02-01",
            "aoi": "95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
            "cloudCoverMax": 150,
        },
    )
    assert response.status_code == 422


@respx.mock
def test_search_endpoint_dispatches_to_demnas_for_demnas_product_types(client):
    respx.get("https://demnas.test/demnas.json").mock(
        return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": []})
    )

    response = client.get(
        "/api/search",
        params={
            "productType": ["DEMNAS_25K"],
            "dateFrom": "2026-01-01",
            "dateUntil": "2026-01-31",
            "aoi": "95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"results": [], "total": 0}


@respx.mock
def test_search_endpoint_accepts_sentinel2_with_cloud_cover_max(client):
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    response = client.get(
        "/api/search",
        params={
            "productType": ["SENTINEL_2_L1C", "SENTINEL_2_L2A"],
            "dateFrom": "2026-01-01",
            "dateUntil": "2026-02-01",
            "aoi": "95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
            "cloudCoverMax": 40,
        },
    )
    assert response.status_code == 200
    assert response.json() == {"results": [], "total": 0}
