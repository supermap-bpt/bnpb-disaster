import httpx
import pytest
import respx

import app.services.demnas as demnas_module
from app.config import Settings
from app.models import ProductType, SearchQuery
from app.services.cache import get_cached_attributes
from app.services.demnas import list_demnas_footprints, search_demnas

SAMPLE_COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "NAMOBJ": "1118-631",
                "NAME_FILE": "DSMHYDRO_32BIT_1118-631.tif",
                "REGION": "SUMATERA",
                "SENSOR": "TERRASAR X",
                "SKALA": "25K",
                "Tahun": "2014",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [95.0, 4.0, 0.0],
                        [96.0, 4.0, 0.0],
                        [96.0, 5.0, 0.0],
                        [95.0, 5.0, 0.0],
                        [95.0, 4.0, 0.0],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "NAMOBJ": "1118-632",
                "NAME_FILE": "DSMHYDRO_32BIT_1118-632.tif",
                "REGION": "SUMATERA",
                "SENSOR": "IFSAR",
                "SKALA": "50K",
                "Tahun": None,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [95.0, 4.0, 0.0],
                        [96.0, 4.0, 0.0],
                        [96.0, 5.0, 0.0],
                        [95.0, 5.0, 0.0],
                        [95.0, 4.0, 0.0],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "NAMOBJ": "9999-999",
                "NAME_FILE": "FAR_AWAY.tif",
                "REGION": "PAPUA",
                "SENSOR": "TERRASAR",
                "SKALA": "25K",
                "Tahun": "2012",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [138.0, -4.0, 0.0],
                        [139.0, -4.0, 0.0],
                        [139.0, -3.0, 0.0],
                        [138.0, -3.0, 0.0],
                        [138.0, -4.0, 0.0],
                    ]
                ],
            },
        },
    ],
}


@pytest.fixture
def settings() -> Settings:
    return Settings(demnas_url="https://demnas.test/demnas.json")


@pytest.fixture(autouse=True)
def _reset_demnas_cache():
    demnas_module._demnas_cache = None
    yield
    demnas_module._demnas_cache = None


async def test_search_demnas_filters_by_skala(settings):
    demnas_module._demnas_cache = SAMPLE_COLLECTION
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="90.0,0.0,145.0,10.0,145.0,-15.0,90.0,-15.0",
    )

    result = await search_demnas(query, settings)

    ids = {item.id for item in result.results}
    assert ids == {"1118-631", "9999-999"}


async def test_search_demnas_recognizes_skala_peta_field_as_an_alternate_scale_source(settings):
    # Real DEMNAS data (verified live): only ~1223 of 4781 tiles use "SKALA"
    # ("25K"/"50K"); ~2930 use "SKALA_PETA" instead ("1:25.000"/"1:50.000"),
    # depending on which regional source layer a tile came from. Both must
    # resolve to the same DEMNAS_25K/50K product types.
    demnas_module._demnas_cache = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "NAMOBJ": "3207-61",
                    "REGION": "PAPUA",
                    "SKALA_PETA": "1:50.000",
                    "THN_DTM": "2011",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[95.0, 4.0, 0.0], [96.0, 4.0, 0.0], [96.0, 5.0, 0.0], [95.0, 5.0, 0.0], [95.0, 4.0, 0.0]]
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "NAMOBJ": "3207-62",
                    "REGION": "PAPUA",
                    "SKALA_PETA": "1:25.000",
                    "THN_DTM": "2011",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[95.0, 4.0, 0.0], [96.0, 4.0, 0.0], [96.0, 5.0, 0.0], [95.0, 5.0, 0.0], [95.0, 4.0, 0.0]]
                    ],
                },
            },
        ],
    }
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K, ProductType.DEMNAS_50K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5",
    )

    result = await search_demnas(query, settings)

    by_id = {item.id: item.productType for item in result.results}
    assert by_id == {"3207-61": ProductType.DEMNAS_50K, "3207-62": ProductType.DEMNAS_25K}


async def test_search_demnas_filters_by_aoi_bbox_overlap(settings):
    demnas_module._demnas_cache = SAMPLE_COLLECTION
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K, ProductType.DEMNAS_50K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5",
    )

    result = await search_demnas(query, settings)

    ids = {item.id for item in result.results}
    assert ids == {"1118-631", "1118-632"}
    assert result.total == 2


async def test_search_demnas_drops_z_coordinate_from_footprint(settings):
    demnas_module._demnas_cache = SAMPLE_COLLECTION
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5",
    )

    result = await search_demnas(query, settings)

    item = next(i for i in result.results if i.id == "1118-631")
    assert item.footprint.coordinates == [
        [[95.0, 4.0], [96.0, 4.0], [96.0, 5.0], [95.0, 5.0], [95.0, 4.0]]
    ]


async def test_search_demnas_paginates_with_skip(settings):
    many_features = [
        {
            "type": "Feature",
            "properties": {"NAMOBJ": f"tile-{i}", "NAME_FILE": f"tile-{i}.tif", "SKALA": "25K", "Tahun": "2010"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[95.0, 4.0, 0.0], [96.0, 4.0, 0.0], [96.0, 5.0, 0.0], [95.0, 5.0, 0.0], [95.0, 4.0, 0.0]]
                ],
            },
        }
        for i in range(120)
    ]
    demnas_module._demnas_cache = {"type": "FeatureCollection", "features": many_features}
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5",
        skip=100,
    )

    result = await search_demnas(query, settings)

    assert result.total == 120
    assert len(result.results) == 20


async def test_search_demnas_ignores_tile_with_null_skala(settings):
    demnas_module._demnas_cache = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"NAMOBJ": "null-skala", "NAME_FILE": "x.tif", "SKALA": None, "Tahun": "2010"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[95.0, 4.0, 0.0], [96.0, 4.0, 0.0], [96.0, 5.0, 0.0], [95.0, 5.0, 0.0], [95.0, 4.0, 0.0]]
                    ],
                },
            }
        ],
    }
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K, ProductType.DEMNAS_50K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5",
    )

    result = await search_demnas(query, settings)

    assert result.results == []
    assert result.total == 0


async def test_search_demnas_uses_year_sentinel_when_no_year_field_present(settings):
    demnas_module._demnas_cache = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"NAMOBJ": "no-year", "NAME_FILE": "x.tif", "SKALA": "25K"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[95.0, 4.0, 0.0], [96.0, 4.0, 0.0], [96.0, 5.0, 0.0], [95.0, 5.0, 0.0], [95.0, 4.0, 0.0]]
                    ],
                },
            }
        ],
    }
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5",
    )

    result = await search_demnas(query, settings)

    assert result.results[0].sensingTime == "0001-01-01T00:00:00Z"


async def test_search_demnas_caches_attributes_generically(settings):
    demnas_module._demnas_cache = SAMPLE_COLLECTION
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5",
    )

    await search_demnas(query, settings)

    attrs = get_cached_attributes("1118-631")
    assert {"Name": "SENSOR", "Value": "TERRASAR X"} in attrs
    assert {"Name": "REGION", "Value": "SUMATERA"} in attrs


@respx.mock
async def test_search_demnas_fetches_and_caches_the_remote_json(settings):
    route = respx.get("https://demnas.test/demnas.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_COLLECTION)
    )
    query = SearchQuery(
        productType=[ProductType.DEMNAS_25K],
        dateFrom="2026-01-01",
        dateUntil="2026-01-31",
        aoi="94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5",
    )

    await search_demnas(query, settings)
    await search_demnas(query, settings)

    assert route.call_count == 1


async def test_list_demnas_footprints_returns_every_match_unpaginated(settings):
    many_features = [
        {
            "type": "Feature",
            "properties": {"NAMOBJ": f"tile-{i}", "NAME_FILE": f"tile-{i}.tif", "SKALA": "25K", "Tahun": "2010"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[95.0, 4.0, 0.0], [96.0, 4.0, 0.0], [96.0, 5.0, 0.0], [95.0, 5.0, 0.0], [95.0, 4.0, 0.0]]
                ],
            },
        }
        for i in range(120)
    ]
    demnas_module._demnas_cache = {"type": "FeatureCollection", "features": many_features}

    result = await list_demnas_footprints(
        [ProductType.DEMNAS_25K], "94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5", settings
    )

    assert result.total == 120
    assert len(result.items) == 120


async def test_list_demnas_footprints_is_lean_and_still_filters_by_skala_and_aoi(settings):
    demnas_module._demnas_cache = SAMPLE_COLLECTION

    result = await list_demnas_footprints(
        [ProductType.DEMNAS_25K], "94.5,3.5,96.5,3.5,96.5,5.5,94.5,5.5", settings
    )

    assert len(result.items) == 1
    item = result.items[0]
    assert item.id == "1118-631"
    assert item.productType == ProductType.DEMNAS_25K
    assert item.footprint.coordinates == [
        [[95.0, 4.0], [96.0, 4.0], [96.0, 5.0], [95.0, 5.0], [95.0, 4.0]]
    ]
