from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.activity_log_repository import ActivityLogRepository
from app.db.models import ActivityLog
from app.db.session import get_db
from app.models import ActivityLogEntry, ActivityLogsListResponse

router = APIRouter()


def _get_repository(session: AsyncSession = Depends(get_db)) -> ActivityLogRepository:
    return ActivityLogRepository(session)


def _to_entry(record: ActivityLog) -> ActivityLogEntry:
    return ActivityLogEntry(
        id=str(record.id),
        action=record.action,
        category=record.category,
        status=record.status,
        description=record.description,
        progress=record.progress,
        createdAt=record.created_at,
    )


@router.get(
    "/api/logs",
    response_model=ActivityLogsListResponse,
    tags=["Logs"],
    summary="List recent activity logs",
)
async def list_logs(
    repository: ActivityLogRepository = Depends(_get_repository),
) -> ActivityLogsListResponse:
    records = await repository.list_recent()
    return ActivityLogsListResponse(items=[_to_entry(r) for r in records], total=len(records))
