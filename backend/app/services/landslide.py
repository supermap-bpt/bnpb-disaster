"""Runs the SNAP landslide change-detection graph as a headless background job.

Modelled on ``product_file.cache_product_file``: an asyncio background task that
shells out to ESA SNAP's ``gpt``, streams progress into both the LandslideJob row
and an ActivityLog entry, and marks the job completed/failed at the end.
"""
import asyncio
import logging
import re
import uuid
from pathlib import Path

from app.config import Settings
from app.db.landslide_repository import LandslideJobRepository
from app.db.repository import SatelliteRepository
from app.db.session import get_sessionmaker
from app.services.activity_log import activity_log
from app.services.snap_graph import build_change_detection_graph, build_preprocess_graph

logger = logging.getLogger(__name__)

# Strong refs to in-flight tasks so asyncio's internal weak ref does not let a
# multi-minute SNAP run be garbage-collected. See product_file.py for rationale.
_background_tasks: set[asyncio.Task] = set()

_PROGRESS_RE = re.compile(rb"(\d{1,3})%")

# Absolute storage root for landslide outputs, relative to the backend cwd.
LANDSLIDE_STORAGE_ROOT = Path("storage/landslide")


_GPT_INSTALL_HINT = (
    "Install ESA SNAP (with the Sentinel-1 Toolbox) and set SNAP_GPT_PATH to its "
    "gpt binary, e.g. SNAP_GPT_PATH=/Applications/esa-snap/bin/gpt "
    "(see backend/LANDSLIDE_PROCESSING.md)."
)


async def _verify_snap_gpt(gpt_path: str) -> str | None:
    """Return an error message if `gpt_path` is missing or is not ESA SNAP's gpt
    (e.g. macOS' /usr/sbin/gpt partition tool, which would misread the graph
    file as a subcommand), else None."""
    try:
        process = await asyncio.create_subprocess_exec(
            gpt_path,
            "-h",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        return f"SNAP gpt not found at '{gpt_path}'. {_GPT_INSTALL_HINT}"
    stdout, _ = await process.communicate()
    text = stdout.decode(errors="replace")
    if "Graph Processing Tool" not in text and "gpt <op>|<graph-file>" not in text:
        return (
            f"'{gpt_path}' is not ESA SNAP's gpt (it does not accept graph files). "
            f"{_GPT_INSTALL_HINT}"
        )
    return None


async def _update_job(job_id: uuid.UUID, **fields) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await LandslideJobRepository(session).update(job_id, **fields)


async def _resolve_product_zip(satellite_id: uuid.UUID) -> Path | None:
    """Return the on-disk .SAFE.zip path for a saved satellite, or None if the
    product file has not finished caching."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = await SatelliteRepository(session).get(satellite_id)
        if record is None or record.product_file_status != "completed" or not record.product_file_path:
            return None
        path = Path(record.product_file_path)
        return path if path.exists() else None


# Ordered pipeline stages shown in the UI stepper. Keep in sync with TOTAL_STAGES
# and the frontend LANDSLIDE_STAGES labels.
STAGE_PREPROCESS_PRE = "Preprocess pre-event"
STAGE_PREPROCESS_POST = "Preprocess post-event"
STAGE_CHANGE_DETECTION = "Collocate & change-detection mask"
STAGE_NAMES = [STAGE_PREPROCESS_PRE, STAGE_PREPROCESS_POST, STAGE_CHANGE_DETECTION]
TOTAL_STAGES = len(STAGE_NAMES)


async def _run_gpt_stage(
    job_id: uuid.UUID,
    log,
    gpt_path: str,
    graph_path: Path,
    stage_index: int,
) -> tuple[bool, list[str]]:
    """Run one gpt graph, streaming its progress into the job scaled to the overall
    pipeline (each stage owns 1/TOTAL_STAGES of the 0-100 bar). Returns (ok, tail)."""
    stage_name = STAGE_NAMES[stage_index]
    await _update_job(
        job_id,
        status="processing",
        stage=stage_name,
        stage_index=stage_index,
        message=f"{stage_name}…",
    )
    logger.info("[landslide %s] stage %s/%s: %s", job_id, stage_index + 1, TOTAL_STAGES, stage_name)

    process = await asyncio.create_subprocess_exec(
        gpt_path,
        graph_path.as_posix(),
        "-q",
        "4",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    # gpt streams its progress bar as dots ("....10%....20%") on a SINGLE line with
    # no newline until "done.", so a line-buffered reader would block. Read raw byte
    # chunks: parse "NN%" for live progress, split whole lines for logging/errors.
    last_reported = -1
    tail: list[str] = []
    buffer = b""
    assert process.stdout is not None
    while True:
        chunk = await process.stdout.read(512)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            raw_line, buffer = buffer.split(b"\n", 1)
            line = raw_line.decode(errors="replace").rstrip()
            if line:
                logger.info("[landslide %s] %s", job_id, line)
                tail.append(line)
                del tail[:-40]
        matches = _PROGRESS_RE.findall(chunk)
        if matches:
            stage_pct = min(int(matches[-1]), 100)
            # Scale this stage's 0-100 into its slice of the overall bar; cap at 99
            # until the whole job confirms completion.
            overall = min(int((stage_index + stage_pct / 100) / TOTAL_STAGES * 100), 99)
            if overall >= last_reported + 2:
                last_reported = overall
                await _update_job(job_id, progress=overall, message=f"{stage_name}… {stage_pct}%")
                await log.set_progress(overall, f"{stage_name}… {stage_pct}%")

    return_code = await process.wait()
    logger.info("[landslide %s] stage %s exited with code %s", job_id, stage_index + 1, return_code)
    return return_code == 0, tail


async def run_landslide_job(
    job_id: uuid.UUID,
    pre_satellite_id: uuid.UUID,
    post_satellite_id: uuid.UUID,
    threshold_db: float,
    settings: Settings,
    aoi_bbox: list[float] | None = None,
) -> None:
    async with activity_log(
        action="Process Landslide",
        category="Satellite",
        description="Running SNAP landslide change detection",
    ) as log:
        pre_zip = await _resolve_product_zip(pre_satellite_id)
        post_zip = await _resolve_product_zip(post_satellite_id)
        if pre_zip is None or post_zip is None:
            msg = "Both products must be fully downloaded before processing."
            await log.mark_failed(msg)
            await _update_job(job_id, status="failed", message=msg)
            return

        gpt_error = await _verify_snap_gpt(settings.snap_gpt_path)
        if gpt_error is not None:
            await log.mark_failed(gpt_error)
            await _update_job(job_id, status="failed", message=gpt_error)
            return

        work_dir = LANDSLIDE_STORAGE_ROOT / str(job_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        pre_dim = work_dir / "pre.dim"
        post_dim = work_dir / "post.dim"
        output_path = work_dir / "result.tif"

        # (graph_path, builder) for each stage, in order.
        stage_graphs = [
            (work_dir / "stage1_pre.xml", build_preprocess_graph(pre_zip.as_posix(), pre_dim.as_posix(), aoi_bbox)),
            (work_dir / "stage2_post.xml", build_preprocess_graph(post_zip.as_posix(), post_dim.as_posix(), aoi_bbox)),
            (
                work_dir / "stage3_change.xml",
                build_change_detection_graph(
                    pre_dim.as_posix(),
                    post_dim.as_posix(),
                    output_path.as_posix(),
                    threshold_db,
                    settings.landslide_water_threshold_db,
                ),
            ),
        ]

        logger.info(
            "[landslide %s] pre=%s post=%s threshold=%s aoi=%s",
            job_id, pre_zip, post_zip, threshold_db, aoi_bbox,
        )
        await _update_job(job_id, status="processing", progress=0, message="Starting SNAP…")
        await log.set_progress(0, "Starting SNAP…")

        try:
            for stage_index, (graph_path, graph_xml) in enumerate(stage_graphs):
                graph_path.write_text(graph_xml, encoding="utf-8")
                ok, tail = await _run_gpt_stage(job_id, log, settings.snap_gpt_path, graph_path, stage_index)
                # Confirm the expected artefact for this stage exists.
                expected = [pre_dim, post_dim, output_path][stage_index]
                if not ok or not expected.exists():
                    salient = [ln for ln in tail if "NodeId" in ln or "Error" in ln or "Caused by" in ln]
                    detail = " | ".join((salient or tail)[-6:]) or "no output produced"
                    msg = f"SNAP failed at '{STAGE_NAMES[stage_index]}': {detail}"
                    await log.mark_failed(msg)
                    await _update_job(job_id, status="failed", message=msg)
                    return
        except FileNotFoundError:
            msg = f"SNAP gpt not found at '{settings.snap_gpt_path}'. {_GPT_INSTALL_HINT}"
            await log.mark_failed(msg)
            await _update_job(job_id, status="failed", message=msg)
            return

        await _update_job(
            job_id,
            status="completed",
            progress=100,
            stage=STAGE_CHANGE_DETECTION,
            stage_index=TOTAL_STAGES,
            message="Done",
            result_path=output_path.as_posix(),
        )
        await log.set_progress(100, "Landslide mask ready")


def trigger_landslide_job(
    job_id: uuid.UUID,
    pre_satellite_id: uuid.UUID,
    post_satellite_id: uuid.UUID,
    threshold_db: float,
    settings: Settings,
    aoi_bbox: list[float] | None = None,
) -> None:
    task = asyncio.create_task(
        run_landslide_job(
            job_id, pre_satellite_id, post_satellite_id, threshold_db, settings, aoi_bbox
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
