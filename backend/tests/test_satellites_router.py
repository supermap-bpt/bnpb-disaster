import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import respx
from sqlalchemy import text

from app.services.product_file import trigger_product_file_caching as real_trigger_product_file_caching


@pytest_asyncio.fixture(autouse=True)
async def _clean_table(db_engine):
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM saved_satellites"))
        await conn.execute(text("DELETE FROM activity_logs"))


@pytest.fixture(autouse=True)
def _disable_product_file_caching(monkeypatch):
    monkeypatch.setattr("app.routers.satellites.trigger_product_file_caching", lambda *args, **kwargs: None)


def _save_body(name="Aceh Flood Jan 2025", product_id="router-p1") -> dict:
    return {
        "satelliteName": name,
        "selectedProduct": {
            "id": product_id,
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


def test_save_endpoint_returns_200_with_satellite_id(client):
    response = client.post("/api/satellites/save", json=_save_body())
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["satelliteId"]


def test_save_endpoint_returns_200_with_success_false_on_duplicate_name(client):
    client.post("/api/satellites/save", json=_save_body(name="Dup", product_id="router-p2"))
    response = client.post("/api/satellites/save", json=_save_body(name="Dup", product_id="router-p3"))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "already exists" in body["message"]


def test_save_endpoint_rejects_blank_name_with_422(client):
    body = _save_body()
    body["satelliteName"] = "   "
    response = client.post("/api/satellites/save", json=body)
    assert response.status_code == 422


def test_list_endpoint_returns_saved_satellites(client):
    client.post("/api/satellites/save", json=_save_body(name="List Test", product_id="router-p4"))
    response = client.get("/api/satellites")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["satelliteName"] == "List Test"


def test_get_detail_endpoint_returns_full_record(client):
    save_response = client.post(
        "/api/satellites/save", json=_save_body(name="Detail Test", product_id="router-p5")
    )
    satellite_id = save_response.json()["satelliteId"]

    response = client.get(f"/api/satellites/{satellite_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["satelliteName"] == "Detail Test"
    assert body["downloadSingleFile"] == "S1A_IW_GRDH_1SDV.SAFE"


def test_get_detail_endpoint_returns_404_for_unknown_id(client):
    response = client.get("/api/satellites/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_delete_endpoint_removes_record(client):
    save_response = client.post(
        "/api/satellites/save", json=_save_body(name="Delete Test", product_id="router-p6")
    )
    satellite_id = save_response.json()["satelliteId"]

    response = client.delete(f"/api/satellites/{satellite_id}")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert client.get(f"/api/satellites/{satellite_id}").status_code == 404


def test_delete_endpoint_returns_404_for_unknown_id(client):
    response = client.delete("/api/satellites/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_delete_endpoint_creates_a_completed_activity_log(client):
    save_response = client.post(
        "/api/satellites/save", json=_save_body(name="Delete Log Test", product_id="router-p7")
    )
    satellite_id = save_response.json()["satelliteId"]

    client.delete(f"/api/satellites/{satellite_id}")

    logs_response = client.get("/api/logs")
    logs = logs_response.json()["items"]
    delete_logs = [log for log in logs if log["action"] == "Delete Satellite"]
    assert len(delete_logs) == 1
    assert delete_logs[0]["status"] == "completed"
    assert delete_logs[0]["progress"] == 100


def test_save_endpoint_triggers_product_file_caching(client, monkeypatch):
    captured = {}

    def fake_trigger(satellite_id, product_id, filename, size, directory, settings, token_manager):
        captured["satellite_id"] = satellite_id
        captured["product_id"] = product_id
        captured["filename"] = filename
        captured["size"] = size

    monkeypatch.setattr("app.routers.satellites.trigger_product_file_caching", fake_trigger)

    response = client.post(
        "/api/satellites/save", json=_save_body(name="Trigger Test", product_id="router-trigger-1")
    )

    assert response.status_code == 200
    assert captured["product_id"] == "router-trigger-1"
    assert captured["filename"] == "S1A_IW_GRDH_1SDV.SAFE"
    assert captured["size"] == "1632MB"
    assert str(captured["satellite_id"]) == response.json()["satelliteId"]


def test_save_endpoint_does_not_trigger_caching_on_a_failed_save(client, monkeypatch):
    called = {"count": 0}

    def fake_trigger(*args, **kwargs):
        called["count"] += 1

    monkeypatch.setattr("app.routers.satellites.trigger_product_file_caching", fake_trigger)

    client.post("/api/satellites/save", json=_save_body(name="Dup Trigger", product_id="router-trigger-2"))
    client.post("/api/satellites/save", json=_save_body(name="Dup Trigger", product_id="router-trigger-3"))

    assert called["count"] == 1  # only the first (successful) save triggers it


def test_save_endpoint_sets_file_status_to_downloading(client):
    response = client.post(
        "/api/satellites/save", json=_save_body(name="Status Test", product_id="router-trigger-4")
    )
    satellite_id = response.json()["satelliteId"]

    detail = client.get(f"/api/satellites/{satellite_id}")
    assert detail.json()["fileStatus"] == "downloading"


def test_retry_file_download_endpoint_returns_200_and_retriggers(client, monkeypatch):
    save_response = client.post(
        "/api/satellites/save", json=_save_body(name="Retry Test", product_id="router-retry-1")
    )
    satellite_id = save_response.json()["satelliteId"]

    captured = {}

    def fake_trigger(satellite_id_arg, product_id, filename, size, directory, settings, token_manager):
        captured["satellite_id"] = str(satellite_id_arg)

    monkeypatch.setattr("app.routers.satellites.trigger_product_file_caching", fake_trigger)

    response = client.post(f"/api/satellites/{satellite_id}/retry-file-download")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert captured["satellite_id"] == satellite_id


def test_retry_file_download_endpoint_returns_404_for_unknown_id(client):
    response = client.post("/api/satellites/00000000-0000-0000-0000-000000000000/retry-file-download")
    assert response.status_code == 404


def test_list_endpoint_includes_file_status(client):
    client.post(
        "/api/satellites/save", json=_save_body(name="File Status List Test", product_id="router-trigger-5")
    )

    response = client.get("/api/satellites")

    assert response.status_code == 200
    assert "fileStatus" in response.json()["items"][0]


def test_list_endpoint_filters_by_name(client):
    client.post("/api/satellites/save", json=_save_body(name="Aceh Flood", product_id="filter-p1"))
    client.post("/api/satellites/save", json=_save_body(name="Jakarta Flood", product_id="filter-p2"))

    response = client.get("/api/satellites", params={"name": "aceh"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["satelliteName"] == "Aceh Flood"


def test_list_endpoint_filters_by_date_range(client):
    early = _save_body(name="Early Save", product_id="filter-date-1")
    early["selectedProduct"]["sensingTime"] = "2025-01-05T00:00:00Z"
    late = _save_body(name="Late Save", product_id="filter-date-2")
    late["selectedProduct"]["sensingTime"] = "2025-03-05T00:00:00Z"
    client.post("/api/satellites/save", json=early)
    client.post("/api/satellites/save", json=late)

    response = client.get(
        "/api/satellites", params={"dateFrom": "2025-01-01", "dateUntil": "2025-01-31"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["satelliteName"] == "Early Save"


def test_list_endpoint_rejects_date_until_before_date_from(client):
    response = client.get(
        "/api/satellites", params={"dateFrom": "2025-02-01", "dateUntil": "2025-01-01"}
    )
    assert response.status_code == 422


def test_list_endpoint_paginates(client):
    for i in range(3):
        client.post(
            "/api/satellites/save", json=_save_body(name=f"Page Sat {i}", product_id=f"page-p{i}")
        )

    response = client.get("/api/satellites", params={"page": 1, "pageSize": 2})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["pageSize"] == 2


def test_list_endpoint_defaults_to_page_1_size_10(client):
    client.post("/api/satellites/save", json=_save_body(name="Default Page Test", product_id="default-page-p1"))

    response = client.get("/api/satellites")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["pageSize"] == 10


def test_download_file_endpoint_returns_404_for_unknown_id(client):
    response = client.get("/api/satellites/00000000-0000-0000-0000-000000000000/download-file")
    assert response.status_code == 404


def test_download_file_endpoint_returns_409_when_not_completed(client):
    save_response = client.post(
        "/api/satellites/save", json=_save_body(name="Not Ready Test", product_id="dl-file-p1")
    )
    satellite_id = save_response.json()["satelliteId"]
    # save_satellite_endpoint sets fileStatus to "downloading" and the autouse
    # _disable_product_file_caching fixture prevents the real background task
    # from running, so the row stays "downloading" indefinitely - exactly the
    # not-yet-cached state this test needs. No DB access outside `client` here.

    response = client.get(f"/api/satellites/{satellite_id}/download-file")

    assert response.status_code == 409


def _save_and_wait_for_cached_file(client, monkeypatch, *, name: str, product_id: str, content: bytes) -> str:
    """Re-enables the real background caching task (respx-mocked CDSE calls) for
    one test, saves a satellite, and polls via `client` (never a second event
    loop) until product_file_status becomes "completed". Returns the satellite id."""
    monkeypatch.setattr("app.routers.satellites.trigger_product_file_caching", real_trigger_product_file_caching)
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 600})
    )
    respx.get(f"https://catalogue.test/Products({product_id})/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": f"https://download.test/Products({product_id})/$value"}
        )
    )
    respx.get(f"https://download.test/Products({product_id})/$value").mock(
        return_value=httpx.Response(200, content=content)
    )

    save_response = client.post("/api/satellites/save", json=_save_body(name=name, product_id=product_id))
    satellite_id = save_response.json()["satelliteId"]

    for _ in range(50):
        detail = client.get(f"/api/satellites/{satellite_id}").json()
        if detail["fileStatus"] == "completed":
            return satellite_id
        time.sleep(0.05)
    raise AssertionError("Product file never finished caching in time.")


@respx.mock
def test_download_file_endpoint_returns_404_when_completed_but_file_missing(client, monkeypatch):
    satellite_id = _save_and_wait_for_cached_file(
        client, monkeypatch, name="Missing File Test", product_id="dl-file-p2", content=b"fake-zip-bytes"
    )
    detail = client.get(f"/api/satellites/{satellite_id}").json()
    file_path = Path(detail["directoryPath"]) / f"{detail['downloadSingleFile']}.zip"
    file_path.unlink()

    response = client.get(f"/api/satellites/{satellite_id}/download-file")

    assert response.status_code == 404


@respx.mock
def test_download_file_endpoint_streams_the_cached_file(client, monkeypatch):
    satellite_id = _save_and_wait_for_cached_file(
        client, monkeypatch, name="Streaming Test", product_id="dl-file-p3", content=b"fake-zip-bytes"
    )

    response = client.get(f"/api/satellites/{satellite_id}/download-file")

    assert response.status_code == 200
    assert response.content == b"fake-zip-bytes"
    assert "S1A_IW_GRDH_1SDV.SAFE.zip" in response.headers["content-disposition"]
