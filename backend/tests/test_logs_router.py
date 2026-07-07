import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture(autouse=True)
async def _clean_table(db_engine):
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM activity_logs"))


@pytest.fixture(autouse=True)
def _disable_product_file_caching(monkeypatch):
    monkeypatch.setattr("app.routers.satellites.trigger_product_file_caching", lambda *args, **kwargs: None)


def test_list_logs_returns_empty_when_none_exist(client):
    response = client.get("/api/logs")
    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0}


def test_list_logs_returns_entries_created_via_save(client):
    save_body = {
        "satelliteName": "Logs Router Test",
        "selectedProduct": {
            "id": "logs-router-p1",
            "name": "S1A_IW_GRDH_1SDV.SAFE",
            "mission": "Sentinel-1",
            "instrumentName": "SAR",
            "polarisation": "VV&VH",
            "sensingTime": "2025-01-26T11:43:01.722106Z",
            "size": "1632MB",
            "footprint": {"type": "Polygon", "coordinates": [[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0]]]},
            "attributes": [],
        },
    }
    client.post("/api/satellites/save", json=save_body)

    response = client.get("/api/logs")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["action"] == "Save Satellite"
    assert entry["category"] == "Satellite"
    assert entry["status"] == "completed"
    assert entry["progress"] == 100
    assert "createdAt" in entry
