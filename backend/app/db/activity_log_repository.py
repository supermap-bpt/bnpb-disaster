import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActivityLog


class ActivityLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, action: str, category: str, description: str) -> ActivityLog:
        record = ActivityLog(
            id=uuid.uuid4(),
            action=action,
            category=category,
            status="in_progress",
            description=description,
            progress=0,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def update_progress(
        self,
        log_id: uuid.UUID,
        *,
        progress: int,
        description: str | None = None,
        status: str | None = None,
    ) -> None:
        record = await self._session.get(ActivityLog, log_id)
        if record is None:
            return
        record.progress = progress
        if description is not None:
            record.description = description
        if status is not None:
            record.status = status
        await self._session.commit()

    async def list_recent(self, limit: int = 100) -> list[ActivityLog]:
        result = await self._session.execute(
            select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
