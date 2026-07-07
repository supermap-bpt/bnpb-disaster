import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.activity_log_repository import ActivityLogRepository
from app.services.activity_log import activity_log

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(autouse=True)
async def _clean_table(db_engine):
    yield
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM activity_logs"))


async def test_clean_exit_marks_completed_with_full_progress(db_session):
    async with activity_log(action="Save Satellite", category="Satellite", description="Saving") as log:
        await log.set_progress(50, "Halfway")

    repository = ActivityLogRepository(db_session)
    records = await repository.list_recent()
    assert len(records) == 1
    assert records[0].status == "completed"
    assert records[0].progress == 100
    assert records[0].description == "Halfway"  # last set_progress description preserved


async def test_explicit_mark_failed_prevents_auto_completion(db_session):
    async with activity_log(action="Save Satellite", category="Satellite", description="Saving") as log:
        await log.set_progress(30, "In progress")
        await log.mark_failed("Something went wrong")
        assert log.is_terminal is True

    repository = ActivityLogRepository(db_session)
    records = await repository.list_recent()
    assert records[0].status == "failed"
    assert records[0].description == "Something went wrong"
    assert records[0].progress == 30  # preserved, not reset


async def test_raised_exception_marks_failed_and_reraises(db_session):
    with pytest.raises(ValueError, match="boom"):
        async with activity_log(action="Download Product", category="Satellite", description="Downloading") as log:
            await log.set_progress(20, "Downloading")
            raise ValueError("boom")

    repository = ActivityLogRepository(db_session)
    records = await repository.list_recent()
    assert records[0].status == "failed"
    assert records[0].description == "boom"
    assert records[0].progress == 20
