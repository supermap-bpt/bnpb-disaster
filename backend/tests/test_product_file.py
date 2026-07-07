import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import respx
from sqlalchemy import text

from app.auth import DownloadTokenManager
from app.config import Settings
from app.db.activity_log_repository import ActivityLogRepository
from app.db.repository import SatelliteRepository
from app.services.product_file import cache_product_file, trigger_product_file_caching

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
        cdse_catalogue_url="https://catalogue.test/Products",
    )


def _sample_fields(**overrides) -> dict:
    fields = dict(
        id=uuid.uuid4(),
        satellite_name="Aceh Flood Jan 2025",
        product_id="p1",
        directory_path="storage/satellites/abc",
        summary=[{"label": "Name", "value": "p1.SAFE"}],
        product=[],
        instrument=[],
        platform=[],
        other=[],
        download_single_file="p1.SAFE",
        preview=None,
        footprint={"type": "Polygon", "coordinates": [[[95.0, 4.0], [98.0, 4.0], [98.0, 6.0]]]},
        mission="Sentinel-1",
        instrument_name="SAR",
        polarisation="VV&VH",
        sensing_time=datetime(2025, 1, 26, 11, 43, 1, tzinfo=timezone.utc),
        size="1632MB",
    )
    fields.update(overrides)
    return fields


@respx.mock
async def test_cache_product_file_writes_file_and_marks_completed(db_session, tmp_path):
    repository = SatelliteRepository(db_session)
    record = await repository.create(**_sample_fields(id=uuid.uuid4(), product_id="cache-p1"))
    directory = tmp_path / "sat-1"
    directory.mkdir()

    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products(cache-p1)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Products(cache-p1)/$value"}
        )
    )
    respx.get("https://download.test/Products(cache-p1)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-zip-bytes" * 100)
    )

    await cache_product_file(
        record.id, "cache-p1", "S1A_TEST.SAFE", "1632MB", directory, _settings(), DownloadTokenManager(_settings())
    )

    written_file = directory / "S1A_TEST.SAFE.zip"
    assert written_file.exists()
    assert written_file.read_bytes() == b"fake-zip-bytes" * 100

    # cache_product_file() writes through a separate session (get_sessionmaker());
    # refresh this test's own copy of the row so the check below observes that
    # session's committed changes instead of the stale pre-update instance still
    # cached in db_session's identity map.
    await db_session.refresh(record)
    fetched = await repository.get(record.id)
    assert fetched.product_file_status == "completed"
    assert fetched.product_file_path == written_file.as_posix()

    log_repository = ActivityLogRepository(db_session)
    logs = await log_repository.list_recent()
    cache_logs = [log for log in logs if log.action == "Cache Product File"]
    assert len(cache_logs) == 1
    assert cache_logs[0].status == "completed"
    assert cache_logs[0].progress == 100
    assert cache_logs[0].description == "Caching S1A_TEST.SAFE.zip (1632MB)"


@respx.mock
async def test_cache_product_file_marks_failed_on_upstream_error(db_session, tmp_path):
    repository = SatelliteRepository(db_session)
    record = await repository.create(**_sample_fields(id=uuid.uuid4(), product_id="cache-p2"))
    # The router sets the row to "downloading" before triggering the background task;
    # reproduce that precondition here rather than leaving product_file_status at None.
    await repository.update_file_status(record.id, status="downloading")
    directory = tmp_path / "sat-2"
    directory.mkdir()

    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products(cache-p2)/$value").mock(return_value=httpx.Response(404))

    await cache_product_file(
        record.id, "cache-p2", "S1A_TEST.SAFE", "1632MB", directory, _settings(), DownloadTokenManager(_settings())
    )

    assert not (directory / "S1A_TEST.SAFE.zip").exists()

    # cache_product_file() writes the failure status through a separate session
    # (get_sessionmaker()); refresh this test's own copy of the row so the check
    # below observes that session's committed changes instead of the stale
    # pre-update instance still cached in db_session's identity map.
    await db_session.refresh(record)
    fetched = await repository.get(record.id)
    assert fetched.product_file_status == "failed"

    log_repository = ActivityLogRepository(db_session)
    logs = await log_repository.list_recent()
    cache_logs = [log for log in logs if log.action == "Cache Product File"]
    assert len(cache_logs) == 1
    assert cache_logs[0].status == "failed"


@respx.mock
async def test_cache_product_file_discards_file_when_satellite_already_deleted(db_session, tmp_path):
    repository = SatelliteRepository(db_session)
    record = await repository.create(**_sample_fields(id=uuid.uuid4(), product_id="cache-p3"))
    directory = tmp_path / "sat-3"
    directory.mkdir()
    await repository.delete(record.id)  # simulates a delete that races the in-flight download

    respx.post("https://identity.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 600})
    )
    respx.get("https://catalogue.test/Products(cache-p3)/$value").mock(
        return_value=httpx.Response(
            301, headers={"Location": "https://download.test/Products(cache-p3)/$value"}
        )
    )
    respx.get("https://download.test/Products(cache-p3)/$value").mock(
        return_value=httpx.Response(200, content=b"fake-zip-bytes")
    )

    await cache_product_file(
        record.id, "cache-p3", "S1A_TEST.SAFE", "1632MB", directory, _settings(), DownloadTokenManager(_settings())
    )

    assert not (directory / "S1A_TEST.SAFE.zip").exists()
    assert await repository.get(record.id) is None  # not resurrected


def test_trigger_product_file_caching_schedules_a_background_task(monkeypatch):
    captured = {}

    class _FakeTask:
        def add_done_callback(self, callback):
            captured["callback"] = callback

    def fake_create_task(coro):
        captured["coro"] = coro
        coro.close()  # avoid an "never awaited" warning; we only assert scheduling happened
        return _FakeTask()

    monkeypatch.setattr("app.services.product_file.asyncio.create_task", fake_create_task)

    trigger_product_file_caching(
        uuid.uuid4(),
        "prod-1",
        "S1A_TEST.SAFE",
        "1632MB",
        Path("storage/satellites/x"),
        _settings(),
        DownloadTokenManager(_settings()),
    )

    assert captured["coro"].cr_code.co_name == "cache_product_file"
    assert callable(captured["callback"])  # done callback registered to release the strong ref
