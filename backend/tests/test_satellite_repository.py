import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.repository import DuplicateSatelliteNameError, SatelliteRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(autouse=True)
async def _clean_table(db_engine):
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM saved_satellites"))


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


async def test_create_and_get_roundtrip(db_session):
    repository = SatelliteRepository(db_session)
    created = await repository.create(**_sample_fields())

    fetched = await repository.get(created.id)

    assert fetched is not None
    assert fetched.satellite_name == "Aceh Flood Jan 2025"
    assert fetched.mission == "Sentinel-1"


async def test_get_returns_none_for_unknown_id(db_session):
    repository = SatelliteRepository(db_session)
    assert await repository.get(uuid.uuid4()) is None


async def test_create_raises_on_duplicate_name(db_session):
    repository = SatelliteRepository(db_session)
    await repository.create(**_sample_fields())

    with pytest.raises(DuplicateSatelliteNameError):
        await repository.create(**_sample_fields(id=uuid.uuid4(), product_id="p2"))


async def test_list_filtered_returns_all_when_no_filters(db_session):
    repository = SatelliteRepository(db_session)
    await repository.create(**_sample_fields())
    await repository.create(**_sample_fields(id=uuid.uuid4(), satellite_name="Other Name", product_id="p2"))

    records, total = await repository.list_filtered()

    assert len(records) == 2
    assert total == 2


async def test_list_filtered_matches_name_case_insensitively(db_session):
    repository = SatelliteRepository(db_session)
    await repository.create(**_sample_fields(satellite_name="Aceh Flood Jan 2025"))
    await repository.create(**_sample_fields(id=uuid.uuid4(), satellite_name="Jakarta Flood Feb 2025", product_id="p2"))

    records, total = await repository.list_filtered(name="aceh")

    assert total == 1
    assert records[0].satellite_name == "Aceh Flood Jan 2025"


async def test_list_filtered_matches_name_substring(db_session):
    repository = SatelliteRepository(db_session)
    await repository.create(**_sample_fields(satellite_name="Aceh Flood Jan 2025"))

    records, total = await repository.list_filtered(name="Flood")

    assert total == 1


async def test_list_filtered_by_date_range_is_inclusive_of_both_boundary_days(db_session):
    repository = SatelliteRepository(db_session)
    await repository.create(
        **_sample_fields(
            satellite_name="Boundary Sat 1",
            sensing_time=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
    )
    await repository.create(
        **_sample_fields(
            id=uuid.uuid4(),
            satellite_name="Boundary Sat 2",
            product_id="p2",
            sensing_time=datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
        )
    )
    await repository.create(
        **_sample_fields(
            id=uuid.uuid4(),
            satellite_name="Boundary Sat 3",
            product_id="p3",
            sensing_time=datetime(2025, 2, 1, 0, 0, 1, tzinfo=timezone.utc),
        )
    )

    records, total = await repository.list_filtered(
        date_from=date(2025, 1, 1), date_until=date(2025, 1, 31)
    )

    assert total == 2


async def test_list_filtered_paginates_with_correct_total(db_session):
    repository = SatelliteRepository(db_session)
    for i in range(3):
        await repository.create(**_sample_fields(id=uuid.uuid4(), satellite_name=f"Sat {i}", product_id=f"page-p{i}"))

    records, total = await repository.list_filtered(offset=0, limit=2)

    assert len(records) == 2
    assert total == 3  # total reflects the full filtered set, not the page size


async def test_list_filtered_combines_name_and_date_filters(db_session):
    repository = SatelliteRepository(db_session)
    await repository.create(
        **_sample_fields(
            satellite_name="Aceh Flood Jan 2025",
            sensing_time=datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc),
        )
    )
    await repository.create(
        **_sample_fields(
            id=uuid.uuid4(),
            product_id="p2",
            satellite_name="Aceh Flood Feb 2025",
            sensing_time=datetime(2025, 2, 15, 0, 0, 0, tzinfo=timezone.utc),
        )
    )

    records, total = await repository.list_filtered(
        name="Aceh", date_from=date(2025, 1, 1), date_until=date(2025, 1, 31)
    )

    assert total == 1
    assert records[0].satellite_name == "Aceh Flood Jan 2025"


async def test_delete_removes_record_and_returns_true(db_session):
    repository = SatelliteRepository(db_session)
    created = await repository.create(**_sample_fields())

    deleted = await repository.delete(created.id)

    assert deleted is True
    assert await repository.get(created.id) is None


async def test_delete_returns_false_for_unknown_id(db_session):
    repository = SatelliteRepository(db_session)
    assert await repository.delete(uuid.uuid4()) is False


async def test_update_file_status_sets_status_only(db_session):
    repository = SatelliteRepository(db_session)
    created = await repository.create(**_sample_fields())

    await repository.update_file_status(created.id, status="downloading")

    fetched = await repository.get(created.id)
    assert fetched.product_file_status == "downloading"
    assert fetched.product_file_path is None


async def test_update_file_status_sets_status_and_path(db_session):
    repository = SatelliteRepository(db_session)
    created = await repository.create(**_sample_fields())

    await repository.update_file_status(
        created.id, status="completed", file_path="storage/satellites/abc/product.zip"
    )

    fetched = await repository.get(created.id)
    assert fetched.product_file_status == "completed"
    assert fetched.product_file_path == "storage/satellites/abc/product.zip"


async def test_update_file_status_is_a_noop_for_unknown_id(db_session):
    repository = SatelliteRepository(db_session)
    # Must not raise.
    await repository.update_file_status(uuid.uuid4(), status="failed")
