import asyncio
import logging
import uuid
from pathlib import Path

import httpx

from app.auth import DownloadTokenManager
from app.config import Settings
from app.db.repository import SatelliteRepository
from app.db.session import get_sessionmaker
from app.services.activity_log import activity_log
from app.services.download import open_download_stream, should_report_progress

logger = logging.getLogger(__name__)

# Strong references to in-flight background caching tasks. asyncio.create_task()
# only holds a weak reference internally, so without this the task object can be
# garbage-collected mid-download (a real risk for a multi-minute 1-2GB transfer).
# See: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
_background_tasks: set[asyncio.Task] = set()


async def _mark_file_status_failed(satellite_id: uuid.UUID) -> None:
    """Best-effort update of the SavedSatellite row's product_file_status to "failed".

    If the record was deleted mid-download, skip the update rather than resurrecting it.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        repository = SatelliteRepository(session)
        record = await repository.get(satellite_id)
        if record is None:
            return
        await repository.update_file_status(satellite_id, status="failed")


async def cache_product_file(
    satellite_id: uuid.UUID,
    product_id: str,
    filename: str,
    size: str,
    directory: Path,
    settings: Settings,
    token_manager: DownloadTokenManager,
) -> None:
    file_path = directory / f"{filename}.zip"
    description = f"Caching {filename}.zip ({size})"

    async with activity_log(
        action="Cache Product File",
        category="Satellite",
        description=description,
    ) as log:
        try:
            client, upstream = await open_download_stream(product_id, settings, token_manager)
        except httpx.HTTPError:
            logger.error("Failed to open download stream for satellite %s", satellite_id, exc_info=True)
            await log.mark_failed("Failed to cache product file: upstream error.")
            await _mark_file_status_failed(satellite_id)
            return

        content_length_header = upstream.headers.get("content-length")
        total_bytes = int(content_length_header) if content_length_header else None
        bytes_written = 0
        last_reported_pct = -1

        try:
            with file_path.open("wb") as fh:
                async for chunk in upstream.aiter_bytes():
                    fh.write(chunk)
                    bytes_written += len(chunk)
                    if total_bytes:
                        pct = min(int(bytes_written / total_bytes * 100), 100)
                        if should_report_progress(pct, last_reported_pct):
                            await log.set_progress(pct, f"Cached {bytes_written} of {total_bytes} bytes")
                            last_reported_pct = pct
        except Exception:
            file_path.unlink(missing_ok=True)
            logger.error("Failed to write product file for satellite %s", satellite_id, exc_info=True)
            await log.mark_failed("Failed to cache product file.")
            await _mark_file_status_failed(satellite_id)
            return
        finally:
            await upstream.aclose()
            await client.aclose()

        # Byte-progress messages above overwrite `description`; restore the
        # size-bearing description as the final one shown once the write completes.
        await log.set_progress(100, description)

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            repository = SatelliteRepository(session)
            record = await repository.get(satellite_id)
            if record is None:
                file_path.unlink(missing_ok=True)
                return
            await repository.update_file_status(
                satellite_id, status="completed", file_path=file_path.as_posix()
            )


def trigger_product_file_caching(
    satellite_id: uuid.UUID,
    product_id: str,
    filename: str,
    size: str,
    directory: Path,
    settings: Settings,
    token_manager: DownloadTokenManager,
) -> None:
    task = asyncio.create_task(
        cache_product_file(satellite_id, product_id, filename, size, directory, settings, token_manager)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
