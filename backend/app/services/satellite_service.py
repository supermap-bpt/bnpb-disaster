import json
import logging
import shutil
import uuid
from pathlib import Path

from app.auth import TokenManager
from app.config import Settings
from app.db.repository import DuplicateSatelliteNameError, SatelliteRepository
from app.models import SaveSatelliteRequest, SaveSatelliteResponse, SelectedProductPayload
from app.services.activity_log import activity_log
from app.services.attribute_grouping import group_attributes
from app.services.cache import cache_footprint, cache_sensing_time, get_cached_product_type
from app.services.render import is_renderable, render_product_image

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path("storage/satellites")


def _build_summary(payload: SelectedProductPayload, platform_rows: list[dict], instrument_rows: list[dict]) -> list[dict]:
    summary = [
        {"label": "Name", "value": payload.name},
        {"label": "Size", "value": payload.size},
        {"label": "Sensing time", "value": payload.sensingTime.isoformat()},
    ]
    summary += [row for row in platform_rows if row["label"] == "Platform short name"]
    summary += [row for row in instrument_rows if row["label"] == "Instrument short name"]
    return summary


async def _try_cache_thumbnail(
    payload: SelectedProductPayload, directory: Path, settings: Settings, token_manager: TokenManager
) -> str | None:
    product_id = payload.id
    product_type = get_cached_product_type(product_id)
    if product_type is None or not is_renderable(product_type):
        return None
    try:
        # render_product_image reads the footprint/sensing time from the cache
        # module (normally populated by a prior search); ensure they're present
        # so a save right after selecting a product can still render a thumbnail.
        cache_footprint(product_id, payload.footprint)
        cache_sensing_time(product_id, payload.sensingTime.isoformat())
        image_bytes = await render_product_image(product_id, product_type, settings, token_manager)
    except Exception:
        logger.warning("Failed to cache thumbnail for product %s", product_id, exc_info=True)
        return None
    thumbnail_path = directory / "thumbnail.jpg"
    thumbnail_path.write_bytes(image_bytes)
    return thumbnail_path.as_posix()


async def save_satellite(
    request: SaveSatelliteRequest,
    repository: SatelliteRepository,
    settings: Settings,
    token_manager: TokenManager,
) -> SaveSatelliteResponse:
    payload = request.selectedProduct
    grouped = group_attributes(payload.attributes)
    summary = _build_summary(payload, grouped.platform, grouped.instrument)

    satellite_id = uuid.uuid4()
    directory = STORAGE_ROOT / str(satellite_id)
    description = f'Saving satellite "{request.satelliteName}" ({payload.size})'

    async with activity_log(
        action="Save Satellite",
        category="Satellite",
        description=description,
    ) as log:
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except OSError:
            logger.error("Failed to create storage folder for satellite %s", satellite_id, exc_info=True)
            await log.mark_failed("Failed to save satellite: could not create storage folder.")
            return SaveSatelliteResponse(
                success=False, message="Failed to save satellite: could not create storage folder."
            )
        await log.set_progress(10, "Folder created")

        try:
            metadata = {"satelliteName": request.satelliteName, "selectedProduct": payload.model_dump(mode="json")}
            (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            await log.set_progress(30, "Metadata written")

            preview_path = await _try_cache_thumbnail(payload, directory, settings, token_manager)
            await log.set_progress(60, "Thumbnail processed")

            record = await repository.create(
                id=satellite_id,
                satellite_name=request.satelliteName,
                product_id=payload.id,
                directory_path=directory.as_posix(),
                summary=summary,
                product=grouped.product,
                instrument=grouped.instrument,
                platform=grouped.platform,
                other=grouped.other,
                download_single_file=payload.name,
                preview=preview_path,
                footprint=payload.footprint.model_dump(),
                mission=payload.mission,
                instrument_name=payload.instrumentName,
                polarisation=payload.polarisation,
                sensing_time=payload.sensingTime,
                size=payload.size,
            )
            await log.set_progress(90, "Saved to database")
            # The progress messages above overwrite `description`; restore the
            # size-bearing description as the final one shown once saving completes.
            await log.set_progress(100, description)
        except DuplicateSatelliteNameError as exc:
            shutil.rmtree(directory, ignore_errors=True)
            await log.mark_failed(str(exc))
            return SaveSatelliteResponse(success=False, message=str(exc))
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            logger.error("Failed to save satellite %s", satellite_id, exc_info=True)
            await log.mark_failed("Failed to save satellite.")
            return SaveSatelliteResponse(success=False, message="Failed to save satellite.")

    return SaveSatelliteResponse(
        success=True, message="Satellite saved successfully.", satelliteId=str(record.id)
    )
