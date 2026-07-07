import uuid

import httpx
import pytest
import pytest_asyncio
import respx
from sqlalchemy import text

from app.auth import TokenManager
from app.config import Settings
from app.db.repository import SatelliteRepository
from app.models import SaveSatelliteRequest
from app.services.satellite_service import save_satellite

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(autouse=True)
async def _clean_table(db_engine):
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM saved_satellites"))
        await conn.execute(text("DELETE FROM activity_logs"))


def _settings() -> Settings:
    return Settings(
        cdse_identity_url="https://identity.test/token",
        cdse_process_url="https://wms.test/process",
    )


def _request(name="Aceh Flood Jan 2025", product_id="service-p1") -> SaveSatelliteRequest:
    return SaveSatelliteRequest.model_validate(
        {
            "satelliteName": name,
            "selectedProduct": {
                "id": product_id,
                "name": "S1A_IW_GRDH_1SDV.SAFE",
                "mission": "Sentinel-1",
                "instrumentName": "SAR",
                "polarisation": "VV&VH",
                "sensingTime": "2025-01-26T11:43:01.722106Z",
                "size": "1632MB",
                "footprint": {
                    "type": "Polygon",
                    "coordinates": [[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0]]],
                },
                "attributes": [{"name": "orbitNumber", "value": "57694"}],
            },
        }
    )


async def test_save_satellite_persists_a_row_without_a_cached_product_type(db_session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repository = SatelliteRepository(db_session)

    response = await save_satellite(_request(), repository, _settings(), TokenManager(_settings()))

    assert response.success is True
    assert response.message == "Satellite saved successfully."
    assert response.satelliteId is not None

    record = await repository.get(uuid.UUID(response.satelliteId))
    assert record is not None
    assert record.satellite_name == "Aceh Flood Jan 2025"
    assert record.product == [{"label": "Absolute orbit number", "value": "57694"}]
    assert record.preview is None  # no cached product type -> thumbnail skipped, non-fatal


async def test_save_satellite_returns_failure_response_for_duplicate_name(db_session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repository = SatelliteRepository(db_session)
    await save_satellite(_request("Dup Name", "service-p2"), repository, _settings(), TokenManager(_settings()))

    second = await save_satellite(
        _request("Dup Name", "service-p3"), repository, _settings(), TokenManager(_settings())
    )

    assert second.success is False
    assert "already exists" in second.message
    assert second.satelliteId is None


async def test_save_satellite_writes_metadata_json_to_disk(db_session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repository = SatelliteRepository(db_session)

    response = await save_satellite(
        _request("Metadata Test", "service-p4"), repository, _settings(), TokenManager(_settings())
    )

    record = await repository.get(uuid.UUID(response.satelliteId))
    metadata_file = tmp_path / record.directory_path / "metadata.json"
    assert metadata_file.exists()
    assert "Metadata Test" in metadata_file.read_text(encoding="utf-8")


@respx.mock
async def test_save_satellite_caches_thumbnail_when_product_type_is_cached_grd(
    db_session, tmp_path, monkeypatch
):
    from app.models import ProductType
    from app.services.cache import cache_product_type

    monkeypatch.chdir(tmp_path)
    cache_product_type("service-p5", ProductType.GRD)
    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 600})
    )
    respx.post("https://wms.test/process").mock(
        return_value=httpx.Response(200, content=b"fake-png-bytes", headers={"content-type": "image/png"})
    )
    repository = SatelliteRepository(db_session)

    response = await save_satellite(
        _request("Thumbnail Test", "service-p5"), repository, _settings(), TokenManager(_settings())
    )

    record = await repository.get(uuid.UUID(response.satelliteId))
    assert record.preview is not None
    assert (tmp_path / record.preview).read_bytes() == b"fake-png-bytes"


async def test_save_satellite_creates_a_completed_activity_log_on_success(db_session, tmp_path, monkeypatch):
    from app.db.activity_log_repository import ActivityLogRepository

    monkeypatch.chdir(tmp_path)
    repository = SatelliteRepository(db_session)

    await save_satellite(_request("Log Success Test", "service-p6"), repository, _settings(), TokenManager(_settings()))

    log_repository = ActivityLogRepository(db_session)
    logs = await log_repository.list_recent()
    assert len(logs) == 1
    assert logs[0].action == "Save Satellite"
    assert logs[0].category == "Satellite"
    assert logs[0].status == "completed"
    assert logs[0].progress == 100
    # Regression: intermediate set_progress() calls ("Folder created", "Metadata
    # written", etc.) overwrite `description` — the size-bearing description must
    # be restored as the final one, not left as whatever the last progress step said.
    assert logs[0].description == 'Saving satellite "Log Success Test" (1632MB)'


async def test_save_satellite_creates_a_failed_activity_log_on_duplicate_name(db_session, tmp_path, monkeypatch):
    from app.db.activity_log_repository import ActivityLogRepository

    monkeypatch.chdir(tmp_path)
    repository = SatelliteRepository(db_session)
    await save_satellite(_request("Dup Log Name", "service-p7"), repository, _settings(), TokenManager(_settings()))

    await save_satellite(_request("Dup Log Name", "service-p8"), repository, _settings(), TokenManager(_settings()))

    log_repository = ActivityLogRepository(db_session)
    logs = await log_repository.list_recent()
    assert len(logs) == 2
    failed_logs = [log for log in logs if log.status == "failed"]
    assert len(failed_logs) == 1
    assert "already exists" in failed_logs[0].description
