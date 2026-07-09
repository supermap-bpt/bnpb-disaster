import pytest
from pydantic import ValidationError

from app.models import ProductType, SearchQuery, SaveSatelliteRequest, SelectedProductPayload, Footprint


def test_product_type_accepts_sentinel1_values():
    assert ProductType("SENTINEL_1_SLC") == ProductType.SLC
    assert ProductType("SENTINEL_1_GRD") == ProductType.GRD


def test_product_type_accepts_sentinel2_values():
    assert ProductType("SENTINEL_2_L1C") == ProductType.S2_L1C
    assert ProductType("SENTINEL_2_L2A") == ProductType.S2_L2A


def test_product_type_accepts_sentinel3_values():
    assert ProductType("SENTINEL_3_SLSTR_L2_LST") == ProductType.S3_SLSTR_L2_LST
    assert ProductType("SENTINEL_3_SLSTR_L2_WST") == ProductType.S3_SLSTR_L2_WST


def test_product_type_rejects_unknown_value():
    with pytest.raises(ValueError):
        ProductType("SENTINEL_3_FOO")


def test_search_query_rejects_date_until_before_date_from():
    with pytest.raises(ValidationError):
        SearchQuery(
            productType=[ProductType.GRD],
            dateFrom="2026-02-01",
            dateUntil="2026-01-01",
            aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        )


def test_search_query_accepts_valid_range():
    query = SearchQuery(
        productType=[ProductType.GRD],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    assert query.productType == [ProductType.GRD]


def test_search_query_rejects_empty_product_type_list():
    with pytest.raises(ValidationError):
        SearchQuery(
            productType=[],
            dateFrom="2026-01-01",
            dateUntil="2026-02-01",
            aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
        )


def test_search_query_defaults_cloud_cover_max_to_100():
    query = SearchQuery(
        productType=[ProductType.GRD],
        dateFrom="2026-01-01",
        dateUntil="2026-02-01",
        aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
    )
    assert query.cloudCoverMax == 100


def test_search_query_rejects_cloud_cover_max_above_100():
    with pytest.raises(ValidationError):
        SearchQuery(
            productType=[ProductType.GRD],
            dateFrom="2026-01-01",
            dateUntil="2026-02-01",
            aoi="95.0,4.0,98.0,4.0,98.0,6.0,95.0,6.0",
            cloudCoverMax=150,
        )


def _valid_payload() -> dict:
    return {
        "satelliteName": "  Aceh Flood Jan 2025  ",
        "selectedProduct": {
            "id": "p1",
            "name": "S1A_IW_GRDH_1SDV.SAFE",
            "mission": "Sentinel-1",
            "instrumentName": "SAR",
            "polarisation": "VV&VH",
            "sensingTime": "2025-01-26T11:43:01.722106Z",
            "size": "1632MB",
            "footprint": {"type": "Polygon", "coordinates": [[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0]]]},
            "attributes": [{"name": "orbitNumber", "value": "57694"}],
        },
    }


def test_save_satellite_request_trims_satellite_name():
    request = SaveSatelliteRequest.model_validate(_valid_payload())
    assert request.satelliteName == "Aceh Flood Jan 2025"


def test_save_satellite_request_rejects_blank_name_after_trim():
    payload = _valid_payload()
    payload["satelliteName"] = "   "
    with pytest.raises(ValidationError):
        SaveSatelliteRequest.model_validate(payload)


def test_save_satellite_request_rejects_name_over_100_chars():
    payload = _valid_payload()
    payload["satelliteName"] = "a" * 101
    with pytest.raises(ValidationError):
        SaveSatelliteRequest.model_validate(payload)


def test_selected_product_payload_parses_iso_sensing_time():
    payload = SelectedProductPayload.model_validate(_valid_payload()["selectedProduct"])
    assert payload.sensingTime.year == 2025
