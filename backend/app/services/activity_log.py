import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.db.activity_log_repository import ActivityLogRepository
from app.db.models import ActivityLog
from app.db.session import get_sessionmaker

logger = logging.getLogger(__name__)


class ActivityLogHandle:
    def __init__(self, repository: ActivityLogRepository, record: ActivityLog) -> None:
        self._repository = repository
        self._record_id: uuid.UUID = record.id
        self._current_progress: int = record.progress
        self._terminal = False

    @property
    def is_terminal(self) -> bool:
        return self._terminal

    async def set_progress(self, progress: int, description: str) -> None:
        self._current_progress = progress
        try:
            await self._repository.update_progress(self._record_id, progress=progress, description=description)
        except Exception:
            logger.warning("Failed to update activity log %s progress", self._record_id, exc_info=True)

    async def mark_failed(self, message: str) -> None:
        self._terminal = True
        try:
            await self._repository.update_progress(
                self._record_id, progress=self._current_progress, status="failed", description=message
            )
        except Exception:
            logger.warning("Failed to mark activity log %s as failed", self._record_id, exc_info=True)


@asynccontextmanager
async def activity_log(*, action: str, category: str, description: str) -> AsyncIterator[ActivityLogHandle]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        repository = ActivityLogRepository(session)
        record = await repository.create(action=action, category=category, description=description)
        handle = ActivityLogHandle(repository, record)
        try:
            yield handle
        except Exception as exc:
            if not handle.is_terminal:
                await handle.mark_failed(str(exc))
            raise
        else:
            if not handle.is_terminal:
                try:
                    await repository.update_progress(record.id, progress=100, status="completed")
                except Exception:
                    logger.warning("Failed to mark activity log %s as completed", record.id, exc_info=True)
