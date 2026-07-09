import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LandslideJob


class LandslideJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **fields) -> LandslideJob:
        record = LandslideJob(**fields)
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def get(self, job_id: uuid.UUID) -> LandslideJob | None:
        return await self._session.get(LandslideJob, job_id)

    async def list_all(self) -> list[LandslideJob]:
        stmt = select(LandslideJob).order_by(LandslideJob.created_at.desc())
        return list((await self._session.execute(stmt)).scalars().all())

    async def update(
        self,
        job_id: uuid.UUID,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        result_path: str | None = None,
        stage: str | None = None,
        stage_index: int | None = None,
    ) -> None:
        record = await self._session.get(LandslideJob, job_id)
        if record is None:
            return
        if status is not None:
            record.status = status
        if progress is not None:
            record.progress = progress
        if message is not None:
            record.message = message
        if result_path is not None:
            record.result_path = result_path
        if stage is not None:
            record.stage = stage
        if stage_index is not None:
            record.stage_index = stage_index
        await self._session.commit()

    async def delete(self, job_id: uuid.UUID) -> bool:
        record = await self.get(job_id)
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.commit()
        return True
