import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.activity_log_repository import ActivityLogRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(autouse=True)
async def _clean_table(db_engine):
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM activity_logs"))


async def test_create_sets_in_progress_status_and_zero_progress(db_session):
    repository = ActivityLogRepository(db_session)

    record = await repository.create(action="Save Satellite", category="Satellite", description="Saving satellite \"Test\"")

    assert record.action == "Save Satellite"
    assert record.category == "Satellite"
    assert record.status == "in_progress"
    assert record.description == 'Saving satellite "Test"'
    assert record.progress == 0


async def test_update_progress_updates_progress_and_description(db_session):
    repository = ActivityLogRepository(db_session)
    record = await repository.create(action="Save Satellite", category="Satellite", description="Saving")

    await repository.update_progress(record.id, progress=50, description="Halfway there")

    updated = await db_session.get(type(record), record.id)
    assert updated.progress == 50
    assert updated.description == "Halfway there"
    assert updated.status == "in_progress"


async def test_update_progress_can_set_status(db_session):
    repository = ActivityLogRepository(db_session)
    record = await repository.create(action="Save Satellite", category="Satellite", description="Saving")

    await repository.update_progress(record.id, progress=100, status="completed")

    updated = await db_session.get(type(record), record.id)
    assert updated.status == "completed"
    assert updated.progress == 100


async def test_update_progress_leaves_description_unchanged_when_not_provided(db_session):
    repository = ActivityLogRepository(db_session)
    record = await repository.create(action="Save Satellite", category="Satellite", description="Original description")

    await repository.update_progress(record.id, progress=100, status="completed")

    updated = await db_session.get(type(record), record.id)
    assert updated.description == "Original description"


async def test_update_progress_is_a_no_op_for_unknown_id(db_session):
    repository = ActivityLogRepository(db_session)
    # Should not raise.
    await repository.update_progress(uuid.uuid4(), progress=50)


async def test_list_recent_orders_newest_first(db_session):
    repository = ActivityLogRepository(db_session)
    first = await repository.create(action="Save Satellite", category="Satellite", description="First")
    second = await repository.create(action="Download Product", category="Satellite", description="Second")

    records = await repository.list_recent()

    assert [r.id for r in records] == [second.id, first.id]


async def test_list_recent_respects_limit(db_session):
    repository = ActivityLogRepository(db_session)
    for i in range(3):
        await repository.create(action="Save Satellite", category="Satellite", description=f"Entry {i}")

    records = await repository.list_recent(limit=2)

    assert len(records) == 2
