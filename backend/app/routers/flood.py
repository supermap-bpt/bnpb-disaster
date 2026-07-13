import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.flood_repository import FloodJobRepository
from app.db.models import FloodJob, SavedSatellite
from app.db.repository import SatelliteRepository
from app.db.session import get_db
from app.models import FloodJobResponse, FloodJobsListResponse, ProcessFloodRequest
from app.services.flood import FLOOD_STORAGE_ROOT, trigger_flood_job
from app.services.flood_preview import ensure_kmz, ensure_preview

router = APIRouter()


def _get_job_repository(session: AsyncSession = Depends(get_db)) -> FloodJobRepository:
    return FloodJobRepository(session)


def _get_satellite_repository(session: AsyncSession = Depends(get_db)) -> SatelliteRepository:
    return SatelliteRepository(session)


def _to_response(record: FloodJob) -> FloodJobResponse:
    return FloodJobResponse(
        id=str(record.id),
        name=record.name,
        satelliteId=str(record.satellite_id),
        status=record.status,
        progress=record.progress,
        message=record.message,
        stage=record.stage,
        stageIndex=record.stage_index,
        totalStages=record.total_stages,
        thresholdSigma0=float(record.threshold_sigma0),
        hasResult=record.result_path is not None,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def _parse_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found.") from exc


async def _require_ready_product(repo: SatelliteRepository, satellite_id: uuid.UUID) -> SavedSatellite:
    record = await repo.get(satellite_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Satellite not found.")
    if record.product_file_status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f'Product "{record.satellite_name}" is not fully downloaded yet.',
        )
    return record


@router.post(
    "/api/flood/process",
    response_model=FloodJobResponse,
    tags=["Flood"],
    summary="Start a SNAP flood-extent detection job from a single product",
)
async def process_flood(
    request: ProcessFloodRequest,
    job_repo: FloodJobRepository = Depends(_get_job_repository),
    sat_repo: SatelliteRepository = Depends(_get_satellite_repository),
    settings: Settings = Depends(get_settings),
) -> FloodJobResponse:
    satellite_id = _parse_id(request.satelliteId)
    product = await _require_ready_product(sat_repo, satellite_id)

    name = f"Flood: {product.satellite_name}"
    job = await job_repo.create(
        satellite_id=product.id,
        name=name,
        status="pending",
        threshold_sigma0=str(settings.flood_threshold_sigma0),
    )
    trigger_flood_job(job.id, product.id, settings.flood_threshold_sigma0, settings, request.aoi)
    return _to_response(job)


@router.get(
    "/api/flood/jobs",
    response_model=FloodJobsListResponse,
    tags=["Flood"],
    summary="List flood processing jobs",
)
async def list_jobs(
    job_repo: FloodJobRepository = Depends(_get_job_repository),
) -> FloodJobsListResponse:
    records = await job_repo.list_all()
    items = [_to_response(r) for r in records]
    return FloodJobsListResponse(items=items, total=len(items))


@router.get(
    "/api/flood/jobs/{jobId}",
    response_model=FloodJobResponse,
    tags=["Flood"],
    summary="Get a single flood job",
)
async def get_job(
    jobId: str,
    job_repo: FloodJobRepository = Depends(_get_job_repository),
) -> FloodJobResponse:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _to_response(record)


@router.get(
    "/api/flood/jobs/{jobId}/result",
    tags=["Flood"],
    summary="Download the flood mask GeoTIFF",
)
async def download_result(
    jobId: str,
    job_repo: FloodJobRepository = Depends(_get_job_repository),
) -> FileResponse:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if record.result_path is None:
        raise HTTPException(status_code=409, detail="Result is not ready yet.")
    path = Path(record.result_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file not found on disk.")
    return FileResponse(path, media_type="image/tiff", filename=f"{record.name}.tif")


@router.get(
    "/api/flood/jobs/{jobId}/preview",
    tags=["Flood"],
    summary="Get WGS84 bounds for the flood mask map overlay (generates the PNG on demand)",
)
async def get_preview_meta(
    jobId: str,
    job_repo: FloodJobRepository = Depends(_get_job_repository),
) -> dict:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if record.result_path is None:
        raise HTTPException(status_code=409, detail="Result is not ready yet.")
    work_dir = FLOOD_STORAGE_ROOT / str(record.id)
    bounds = await ensure_preview(work_dir)
    if bounds is None:
        raise HTTPException(status_code=503, detail="Preview unavailable (GDAL missing or render failed).")
    return {"bounds": bounds}


@router.get(
    "/api/flood/jobs/{jobId}/preview.png",
    tags=["Flood"],
    summary="Download the rendered flood mask overlay PNG",
)
async def get_preview_image(
    jobId: str,
    job_repo: FloodJobRepository = Depends(_get_job_repository),
) -> FileResponse:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    work_dir = FLOOD_STORAGE_ROOT / str(record.id)
    if await ensure_preview(work_dir) is None:
        raise HTTPException(status_code=503, detail="Preview unavailable.")
    return FileResponse(work_dir / "preview.png", media_type="image/png")


@router.get(
    "/api/flood/jobs/{jobId}/kmz",
    tags=["Flood"],
    summary="Download the flood mask as a KMZ (Google Earth ground overlay)",
)
async def download_kmz(
    jobId: str,
    job_repo: FloodJobRepository = Depends(_get_job_repository),
) -> FileResponse:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if record.result_path is None:
        raise HTTPException(status_code=409, detail="Result is not ready yet.")
    work_dir = FLOOD_STORAGE_ROOT / str(record.id)
    kmz = await ensure_kmz(work_dir, name=record.name)
    if kmz is None:
        raise HTTPException(status_code=503, detail="KMZ unavailable (GDAL missing or render failed).")
    return FileResponse(kmz, media_type="application/vnd.google-earth.kmz", filename=f"{record.name}.kmz")


@router.delete(
    "/api/flood/jobs/{jobId}",
    tags=["Flood"],
    summary="Delete a flood job and its output files",
)
async def delete_job(
    jobId: str,
    job_repo: FloodJobRepository = Depends(_get_job_repository),
) -> dict[str, bool]:
    job_id = _parse_id(jobId)
    record = await job_repo.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    shutil.rmtree(FLOOD_STORAGE_ROOT / str(job_id), ignore_errors=True)
    await job_repo.delete(job_id)
    return {"success": True}
