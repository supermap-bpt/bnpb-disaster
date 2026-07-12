"""Router-level tests for /api/flood/*.

Fixture conventions verified against test_satellites_router.py / test_logs_router.py
(this codebase's existing router-test files) and backend/tests/conftest.py, NOT
assumed from the task brief's own draft:

- `client` is a *sync* `fastapi.testclient.TestClient` fixture (not an async
  httpx client) - so requests are made as plain `client.post(...)`, never
  `await client.post(...)`.
- There is no `db_session`-in-a-router-test precedent anywhere in this suite.
  conftest.py's `client` fixture docstring explains why: it clears
  `get_engine`'s lru_cache and creates a fresh AsyncEngine bound to the
  TestClient's own portal-thread event loop for every test. `db_session` (used
  only in pure-repository tests, always under
  `pytestmark = pytest.mark.asyncio(loop_scope="session")`) instead binds to
  the shared *session*-scoped fixture event loop. Calling `get_sessionmaker()`
  (which `db_session` does) after `client`'s cache-clear would hand back the
  portal-thread-bound engine, so a session-scoped-loop test body awaiting
  `db_session.commit()` would be operating a connection pool that was actually
  established on a different loop - exactly the "attached to a different loop"
  failure mode the fixture comment warns about. No existing test combines
  `client` and `db_session` in one test; we don't introduce the first one here.
- Instead, to get a SavedSatellite into the "completed" (fully downloaded)
  state the /api/flood/process success-path tests need, we reuse
  test_satellites_router.py's own established pattern: re-enable the real
  `trigger_product_file_caching` background task with `respx`-mocked CDSE
  calls, POST to /api/satellites/save, then poll via `client` (never a second
  event loop) until `fileStatus` flips to "completed". Everything - setup and
  assertions alike - goes through the one `client`-bound engine.
- Cleanup between tests follows the same `_clean_table(db_engine)` autouse
  async-fixture-doing-raw-SQL-in-teardown pattern used by
  test_satellites_router.py/test_logs_router.py.
"""
import time

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
        await conn.execute(text("DELETE FROM flood_jobs"))
        await conn.execute(text("DELETE FROM saved_satellites"))
        await conn.execute(text("DELETE FROM activity_logs"))


@pytest.fixture(autouse=True)
def _disable_product_file_caching(monkeypatch):
    monkeypatch.setattr("app.routers.satellites.trigger_product_file_caching", lambda *args, **kwargs: None)


def _save_body(name: str, product_id: str) -> dict:
    return {
        "satelliteName": name,
        "selectedProduct": {
            "id": product_id,
            "name": "S1A_IW_GRDH_1SDV.SAFE",
            "mission": "Sentinel-1",
            "instrumentName": "SAR",
            "polarisation": "VV",
            "sensingTime": "2025-01-14T00:00:00Z",
            "size": "1632MB",
            "footprint": {
                "type": "Polygon",
                "coordinates": [[[97.5, 4.0], [98.3, 4.0], [98.3, 5.0], [97.5, 5.0]]],
            },
            "attributes": [],
        },
    }


def _save_and_wait_for_completed_satellite(client, monkeypatch, *, name: str, product_id: str) -> str:
    """Mirrors test_satellites_router.py's `_save_and_wait_for_cached_file`: drives
    the real product-file caching pipeline (respx-mocked CDSE calls) through
    `client` only, then polls until the satellite's fileStatus is "completed"."""
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
        return_value=httpx.Response(200, content=b"fake-zip-bytes")
    )

    save_response = client.post("/api/satellites/save", json=_save_body(name, product_id))
    satellite_id = save_response.json()["satelliteId"]

    for _ in range(50):
        detail = client.get(f"/api/satellites/{satellite_id}").json()
        if detail["fileStatus"] == "completed":
            return satellite_id
        time.sleep(0.05)
    raise AssertionError("Product file never finished caching in time.")


@respx.mock
def test_process_flood_creates_a_pending_job(client, monkeypatch):
    satellite_id = _save_and_wait_for_completed_satellite(
        client, monkeypatch, name="Aceh Tamiang Flood 14 Jan", product_id="flood-p1"
    )
    monkeypatch.setattr("app.routers.flood.trigger_flood_job", lambda *a, **k: None)

    response = client.post(
        "/api/flood/process", json={"satelliteId": satellite_id, "aoi": [97.5, 4.0, 98.3, 5.0]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["totalStages"] == 8
    assert body["hasResult"] is False


def test_process_flood_rejects_a_not_yet_downloaded_product(client):
    save_response = client.post(
        "/api/satellites/save", json=_save_body("Not Ready Flood", "flood-p2")
    )
    satellite_id = save_response.json()["satelliteId"]
    # _disable_product_file_caching (autouse) prevents the background task
    # from ever running, so the row stays "downloading" - the not-yet-cached
    # state this test needs. No DB access outside `client` here.

    response = client.post("/api/flood/process", json={"satelliteId": satellite_id})

    assert response.status_code == 409


@respx.mock
def test_list_flood_jobs_returns_created_jobs(client, monkeypatch):
    satellite_id = _save_and_wait_for_completed_satellite(
        client, monkeypatch, name="List Flood Test", product_id="flood-p3"
    )
    monkeypatch.setattr("app.routers.flood.trigger_flood_job", lambda *a, **k: None)
    client.post("/api/flood/process", json={"satelliteId": satellite_id})

    response = client.get("/api/flood/jobs")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["satelliteId"] == satellite_id


@respx.mock
def test_delete_flood_job_removes_it(client, monkeypatch):
    satellite_id = _save_and_wait_for_completed_satellite(
        client, monkeypatch, name="Delete Flood Test", product_id="flood-p4"
    )
    monkeypatch.setattr("app.routers.flood.trigger_flood_job", lambda *a, **k: None)
    created = client.post("/api/flood/process", json={"satelliteId": satellite_id}).json()

    response = client.delete(f"/api/flood/jobs/{created['id']}")

    assert response.status_code == 200
    assert client.get(f"/api/flood/jobs/{created['id']}").status_code == 404
