import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.landslide_repository import LandslideJobRepository
from app.db.models import LandslideJob, SavedSatellite
from app.db.repository import SatelliteRepository
from app.db.session import get_db
from app.models import (
    LandslideJobResponse,
    LandslideJobsListResponse,
    ProcessLandslideRequest,
)
from app.services.landslide import LANDSLIDE_STORAGE_ROOT, trigger_landslide_job
from app.services.landslide_preview import ensure_kmz, ensure_preview

router = APIRouter()


def _get_job_repository(session: AsyncSession = Depends(get_db)) -> LandslideJobRepository:
    return LandslideJobRepository(session)


def _get_satellite_repository(session: AsyncSession = Depends(get_db)) -> SatelliteRepository:
    return SatelliteRepository(session)


def _to_response(record: LandslideJob) -> LandslideJobResponse:
    return LandslideJobResponse(
        id=str(record.id),
        name=record.name,
        preSatelliteId=str(record.pre_satellite_id),
        postSatelliteId=str(record.post_satellite_id),
        status=record.status,
        progress=record.progress,
        message=record.message,
        stage=record.stage,
        stageIndex=record.stage_index,
        totalStages=record.total_stages,
        thresholdDb=float(record.threshold_db),
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
    "/api/landslide/process",
    response_model=LandslideJobResponse,
    tags=["Landslide"],
    summary="Start a SNAP landslide change-detection job from a pre/post product pair",
)
async def process_landslide(
    request: ProcessLandslideRequest,
    job_repo: LandslideJobRepository = Depends(_get_job_repository),
    sat_repo: SatelliteRepository = Depends(_get_satellite_repository),
    settings: Settings = Depends(get_settings),
) -> LandslideJobResponse:
    id_a = _parse_id(request.preSatelliteId)
    id_b = _parse_id(request.postSatelliteId)
    product_a = await _require_ready_product(sat_repo, id_a)
    product_b = await _require_ready_product(sat_repo, id_b)

    # Order chronologically regardless of selection order: earlier = pre, later = post.
    if product_a.sensing_time <= product_b.sensing_time:
        pre, post = product_a, product_b
    else:
        pre, post = product_b, product_a

    name = f"Landslide: {pre.satellite_name} → {post.satellite_name}"
    job = await job_repo.create(
        pre_satellite_id=pre.id,
        post_satellite_id=post.id,
        name=name,
        status="pending",
        threshold_db=str(settings.landslide_threshold_db),
    )
    trigger_landslide_job(
        job.id, pre.id, post.id, settings.landslide_threshold_db, settings, request.aoi
    )
    return _to_response(job)


@router.get(
    "/api/landslide/jobs",
    response_model=LandslideJobsListResponse,
    tags=["Landslide"],
    summary="List landslide processing jobs",
)
async def list_jobs(
    job_repo: LandslideJobRepository = Depends(_get_job_repository),
) -> LandslideJobsListResponse:
    records = await job_repo.list_all()
    items = [_to_response(r) for r in records]
    return LandslideJobsListResponse(items=items, total=len(items))


@router.get(
    "/api/landslide/jobs/{jobId}",
    response_model=LandslideJobResponse,
    tags=["Landslide"],
    summary="Get a single landslide job",
)
async def get_job(
    jobId: str,
    job_repo: LandslideJobRepository = Depends(_get_job_repository),
) -> LandslideJobResponse:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _to_response(record)


@router.get(
    "/api/landslide/jobs/{jobId}/result",
    tags=["Landslide"],
    summary="Download the landslide mask GeoTIFF",
)
async def download_result(
    jobId: str,
    job_repo: LandslideJobRepository = Depends(_get_job_repository),
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
    "/api/landslide/jobs/{jobId}/preview",
    tags=["Landslide"],
    summary="Get WGS84 bounds for the landslide mask map overlay (generates the PNG on demand)",
)
async def get_preview_meta(
    jobId: str,
    job_repo: LandslideJobRepository = Depends(_get_job_repository),
) -> dict:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if record.result_path is None:
        raise HTTPException(status_code=409, detail="Result is not ready yet.")
    work_dir = LANDSLIDE_STORAGE_ROOT / str(record.id)
    bounds = await ensure_preview(work_dir)
    if bounds is None:
        raise HTTPException(status_code=503, detail="Preview unavailable (GDAL missing or render failed).")
    # bounds = [south, west, north, east]
    return {"bounds": bounds}


@router.get(
    "/api/landslide/jobs/{jobId}/preview.png",
    tags=["Landslide"],
    summary="Download the rendered landslide mask overlay PNG",
)
async def get_preview_image(
    jobId: str,
    job_repo: LandslideJobRepository = Depends(_get_job_repository),
) -> FileResponse:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    work_dir = LANDSLIDE_STORAGE_ROOT / str(record.id)
    if await ensure_preview(work_dir) is None:
        raise HTTPException(status_code=503, detail="Preview unavailable.")
    return FileResponse(work_dir / "preview.png", media_type="image/png")


@router.get(
    "/api/landslide/jobs/{jobId}/kmz",
    tags=["Landslide"],
    summary="Download the landslide mask as a KMZ (Google Earth ground overlay)",
)
async def download_kmz(
    jobId: str,
    job_repo: LandslideJobRepository = Depends(_get_job_repository),
) -> FileResponse:
    record = await job_repo.get(_parse_id(jobId))
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if record.result_path is None:
        raise HTTPException(status_code=409, detail="Result is not ready yet.")
    work_dir = LANDSLIDE_STORAGE_ROOT / str(record.id)
    kmz = await ensure_kmz(work_dir, name=record.name)
    if kmz is None:
        raise HTTPException(status_code=503, detail="KMZ unavailable (GDAL missing or render failed).")
    return FileResponse(kmz, media_type="application/vnd.google-earth.kmz", filename=f"{record.name}.kmz")


@router.delete(
    "/api/landslide/jobs/{jobId}",
    tags=["Landslide"],
    summary="Delete a landslide job and its output files",
)
async def delete_job(
    jobId: str,
    job_repo: LandslideJobRepository = Depends(_get_job_repository),
) -> dict[str, bool]:
    job_id = _parse_id(jobId)
    record = await job_repo.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    shutil.rmtree(LANDSLIDE_STORAGE_ROOT / str(job_id), ignore_errors=True)
    await job_repo.delete(job_id)
    return {"success": True}
