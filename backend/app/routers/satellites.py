import shutil
import uuid
from pathlib import Path

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import DownloadTokenManager, TokenManager
from app.config import Settings, get_settings
from app.db.models import SavedSatellite
from app.db.repository import SatelliteRepository
from app.db.session import get_db
from app.models import (
    DeleteSatelliteResponse,
    RetryFileDownloadResponse,
    SaveSatelliteRequest,
    SaveSatelliteResponse,
    SavedSatelliteDetail,
    SavedSatelliteSummary,
    SavedSatellitesListResponse,
)
from app.routers.download import _get_download_token_manager
from app.routers.search import _get_token_manager
from app.services.activity_log import activity_log
from app.services.product_file import trigger_product_file_caching
from app.services.satellite_service import save_satellite

router = APIRouter()


def _get_repository(session: AsyncSession = Depends(get_db)) -> SatelliteRepository:
    return SatelliteRepository(session)


def _to_summary(record: SavedSatellite) -> SavedSatelliteSummary:
    return SavedSatelliteSummary(
        id=str(record.id),
        satelliteName=record.satellite_name,
        mission=record.mission,
        instrumentName=record.instrument_name,
        polarisation=record.polarisation,
        sensingTime=record.sensing_time,
        size=record.size,
        preview=record.preview,
        savedAt=record.saved_at,
        fileStatus=record.product_file_status,
    )


def _to_detail(record: SavedSatellite) -> SavedSatelliteDetail:
    return SavedSatelliteDetail(
        **_to_summary(record).model_dump(),
        productId=record.product_id,
        directoryPath=record.directory_path,
        summary=record.summary,
        product=record.product,
        instrument=record.instrument,
        platform=record.platform,
        other=record.other,
        downloadSingleFile=record.download_single_file,
        footprint=record.footprint,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def _parse_id(satellite_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(satellite_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Satellite not found.") from exc


@router.post(
    "/api/satellites/save",
    response_model=SaveSatelliteResponse,
    tags=["Satellites"],
    summary="Save (bookmark) a selected satellite product",
)
async def save_satellite_endpoint(
    request: SaveSatelliteRequest,
    repository: SatelliteRepository = Depends(_get_repository),
    settings: Settings = Depends(get_settings),
    token_manager: TokenManager = Depends(_get_token_manager),
    download_token_manager: DownloadTokenManager = Depends(_get_download_token_manager),
) -> SaveSatelliteResponse:
    response = await save_satellite(request, repository, settings, token_manager)
    if response.success and response.satelliteId is not None:
        satellite_id = uuid.UUID(response.satelliteId)
        record = await repository.get(satellite_id)
        if record is not None:
            await repository.update_file_status(satellite_id, status="downloading")
            trigger_product_file_caching(
                satellite_id,
                record.product_id,
                record.download_single_file,
                record.size,
                Path(record.directory_path),
                settings,
                download_token_manager,
            )
    return response


@router.get(
    "/api/satellites",
    response_model=SavedSatellitesListResponse,
    tags=["Satellites"],
    summary="List saved satellites",
)
async def list_satellites(
    name: str | None = None,
    dateFrom: date | None = None,
    dateUntil: date | None = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=100),
    repository: SatelliteRepository = Depends(_get_repository),
) -> SavedSatellitesListResponse:
    if dateFrom and dateUntil and dateUntil < dateFrom:
        raise HTTPException(status_code=422, detail="dateUntil must not be before dateFrom.")
    records, total = await repository.list_filtered(
        name=name,
        date_from=dateFrom,
        date_until=dateUntil,
        offset=(page - 1) * pageSize,
        limit=pageSize,
    )
    return SavedSatellitesListResponse(
        items=[_to_summary(r) for r in records], total=total, page=page, pageSize=pageSize
    )


@router.get(
    "/api/satellites/{satelliteId}",
    response_model=SavedSatelliteDetail,
    tags=["Satellites"],
    summary="Get a saved satellite's full detail",
)
async def get_satellite(
    satelliteId: str, repository: SatelliteRepository = Depends(_get_repository)
) -> SavedSatelliteDetail:
    record = await repository.get(_parse_id(satelliteId))
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite not found.")
    return _to_detail(record)


@router.get(
    "/api/satellites/{satelliteId}/download-file",
    tags=["Satellites"],
    summary="Download a saved satellite's locally cached product file",
)
async def download_satellite_file(
    satelliteId: str, repository: SatelliteRepository = Depends(_get_repository)
) -> FileResponse:
    record = await repository.get(_parse_id(satelliteId))
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite not found.")
    if record.product_file_status != "completed":
        raise HTTPException(status_code=409, detail="Product file is not ready for download yet.")
    file_path = Path(record.product_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Cached product file not found on disk.")
    return FileResponse(file_path, media_type="application/octet-stream", filename=file_path.name)


@router.delete(
    "/api/satellites/{satelliteId}",
    response_model=DeleteSatelliteResponse,
    tags=["Satellites"],
    summary="Delete a saved satellite",
)
async def delete_satellite(
    satelliteId: str, repository: SatelliteRepository = Depends(_get_repository)
) -> DeleteSatelliteResponse:
    parsed_id = _parse_id(satelliteId)
    record = await repository.get(parsed_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite not found.")
    directory = Path(record.directory_path)

    async with activity_log(
        action="Delete Satellite",
        category="Satellite",
        description=f'Deleting satellite "{record.satellite_name}"',
    ) as log:
        await repository.delete(parsed_id)
        await log.set_progress(50, "Database record deleted")
        shutil.rmtree(directory, ignore_errors=True)
        await log.set_progress(100, "Storage folder removed")

    return DeleteSatelliteResponse(success=True, message="Satellite deleted successfully.")


@router.post(
    "/api/satellites/{satelliteId}/retry-file-download",
    response_model=RetryFileDownloadResponse,
    tags=["Satellites"],
    summary="Retry caching a saved satellite's product file",
)
async def retry_file_download(
    satelliteId: str,
    repository: SatelliteRepository = Depends(_get_repository),
    settings: Settings = Depends(get_settings),
    download_token_manager: DownloadTokenManager = Depends(_get_download_token_manager),
) -> RetryFileDownloadResponse:
    parsed_id = _parse_id(satelliteId)
    record = await repository.get(parsed_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite not found.")

    await repository.update_file_status(parsed_id, status="downloading")
    trigger_product_file_caching(
        parsed_id,
        record.product_id,
        record.download_single_file,
        record.size,
        Path(record.directory_path),
        settings,
        download_token_manager,
    )
    return RetryFileDownloadResponse(success=True, message="File download restarted.")
