"""Runs the SNAP flood-extent-detection graph as a headless background job,
over a single Sentinel-1 GRD product (unlike landslide.py's pre/post pair) -
8 stages, run strictly sequentially (no parallel track/barrier-sync logic
needed, since there is only one product).

Reuses landslide.py's already-generic, already-tested subprocess machinery
directly: _verify_snap_gpt (gpt binary sanity check) and
_run_gpt_process_blocking (the classic-subprocess-via-thread-executor pattern -
the root-cause fix for asyncio.create_subprocess_exec's Windows
NotImplementedError, plus "NN%" progress-marker parsing). Neither of those is
Landslide-specific - importing them here avoids duplicating the same
subprocess/progress-parsing logic in a second file.

_run_gpt_stage, by contrast, is defined locally below rather than imported:
landslide's version hardcodes references to landslide's own module-level
STAGE_NAMES (7 entries)/TOTAL_STAGES(7) and landslide's own _update_job
(writes via LandslideJobRepository). Flood has 8 stages, so calling
landslide's version for flood's stage_index=7 (the final Band Maths/mask
stage) raised IndexError - and even for stages 0-6, progress writes went to
LandslideJobRepository against a flood job's id, matching no row and
silently no-op'ing. The local _run_gpt_stage here is functionally identical
to landslide's (same progress-scaling math, same executor-thread pattern)
but closes over FLOOD's own STAGE_NAMES/TOTAL_STAGES/_update_job.
"""
import asyncio
import logging
import uuid
from pathlib import Path

from app.config import Settings
from app.db.flood_repository import FloodJobRepository
from app.db.repository import SatelliteRepository
from app.db.session import get_sessionmaker
from app.services.activity_log import activity_log
from app.services.flood_graph import (
    build_border_noise_graph,
    build_calibration_graph,
    build_flood_mask_graph,
    build_orbit_graph,
    build_speckle_graph,
    build_subset_graph,
    build_terrain_correction_graph,
    build_tnr_graph,
)
from app.services.landslide import (
    _GPT_INSTALL_HINT,
    _run_gpt_process_blocking,
    _verify_snap_gpt,
)

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()

FLOOD_STORAGE_ROOT = Path("storage/flood")

STAGE_TNR = "Thermal Noise Removal"
STAGE_ORBIT = "Apply Orbit File"
STAGE_BORDER_NOISE = "Remove GRD Border Noise"
STAGE_CALIBRATION = "Calibration"
STAGE_SUBSET = "Subset"
STAGE_SPECKLE = "Speckle Filtering"
STAGE_TERRAIN_CORRECTION = "Terrain Correction"
STAGE_MASK = "Band Maths & mask export"
STAGE_NAMES = [
    STAGE_TNR,
    STAGE_ORBIT,
    STAGE_BORDER_NOISE,
    STAGE_CALIBRATION,
    STAGE_SUBSET,
    STAGE_SPECKLE,
    STAGE_TERRAIN_CORRECTION,
    STAGE_MASK,
]
TOTAL_STAGES = len(STAGE_NAMES)

# (stage_index, graph_builder function name, filename tag) for the 7
# preprocessing stages (everything but the final mask/export stage, which
# needs the threshold and writes GeoTIFF instead of BEAM-DIMAP - handled
# separately in run_flood_job). graph_builder(source, output_dim) -> graph
# XML, except stage 4 (Subset) which also takes the optional aoi_bbox.
#
# Builders are looked up by *name* against this module's globals() at call
# time (see run_flood_job's loop), not stored as direct function references
# here - a module-level list of bound references would freeze in the
# original build_*_graph objects at import time, so tests monkeypatching
# e.g. `flood.build_tnr_graph` afterwards would silently miss (this bit
# test_landslide.py's PREPROCESS_STEPS, which works around it by
# monkeypatching the whole list instead; flood.py avoids the pitfall here).
PREPROCESS_STEPS = [
    (0, "build_tnr_graph", "tnr"),
    (1, "build_orbit_graph", "orbit"),
    (2, "build_border_noise_graph", "border"),
    (3, "build_calibration_graph", "cal"),
    (4, "build_subset_graph", "subset"),
    (5, "build_speckle_graph", "speckle"),
    (6, "build_terrain_correction_graph", "tc"),
]


async def _update_job(job_id: uuid.UUID, **fields) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await FloodJobRepository(session).update(job_id, **fields)


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


async def _run_gpt_stage(
    job_id: uuid.UUID,
    log,
    gpt_path: str,
    graph_path: Path,
    stage_index: int,
) -> tuple[bool, list[str]]:
    """Run one gpt graph, streaming its progress into the job scaled to the overall
    pipeline (each stage owns 1/TOTAL_STAGES of the 0-100 bar). Returns (ok, tail).

    Flood-local counterpart to landslide._run_gpt_stage - see this module's
    docstring for why this can't just import landslide's version (it's
    hardcoded to landslide's own 7-stage STAGE_NAMES/TOTAL_STAGES and writes
    via LandslideJobRepository). This closes over FLOOD's STAGE_NAMES/
    TOTAL_STAGES/_update_job instead; the progress-percent parsing itself
    still happens inside the genuinely-generic _run_gpt_process_blocking,
    reused as-is from landslide.py."""
    stage_name = STAGE_NAMES[stage_index]
    await _update_job(
        job_id,
        status="processing",
        stage=stage_name,
        stage_index=stage_index,
        message=f"{stage_name}…",
    )
    logger.info("[flood %s] stage %s/%s: %s", job_id, stage_index + 1, TOTAL_STAGES, stage_name)

    loop = asyncio.get_running_loop()
    last_reported = -1

    def report_progress(stage_pct: int) -> None:
        # Called from the executor's worker thread, not the event loop thread.
        nonlocal last_reported
        # Scale this stage's 0-100 into its slice of the overall bar; cap at 99
        # until the whole job confirms completion.
        overall = min(int((stage_index + stage_pct / 100) / TOTAL_STAGES * 100), 99)
        if overall >= last_reported + 2:
            last_reported = overall
            message = f"{stage_name}… {stage_pct}%"

            async def _post() -> None:
                await _update_job(job_id, progress=overall, message=message)
                await log.set_progress(overall, message)

            asyncio.run_coroutine_threadsafe(_post(), loop)

    ok, tail = await loop.run_in_executor(
        None, _run_gpt_process_blocking, job_id, stage_name, gpt_path, graph_path, report_progress
    )
    logger.info("[flood %s] stage %s exited ok=%s", job_id, stage_index + 1, ok)
    return ok, tail


async def run_flood_job(
    job_id: uuid.UUID,
    satellite_id: uuid.UUID,
    threshold_sigma0: float,
    settings: Settings,
    aoi_bbox: list[float] | None = None,
) -> None:
    async with activity_log(
        action="Process Flood",
        category="Satellite",
        description="Running SNAP flood-extent detection",
    ) as log:
        product_zip = await _resolve_product_zip(satellite_id)
        if product_zip is None:
            msg = "The product must be fully downloaded before processing."
            await log.mark_failed(msg)
            await _update_job(job_id, status="failed", message=msg)
            return

        gpt_error = await _verify_snap_gpt(settings.snap_gpt_path)
        if gpt_error is not None:
            await log.mark_failed(gpt_error)
            await _update_job(job_id, status="failed", message=gpt_error)
            return

        work_dir = FLOOD_STORAGE_ROOT / str(job_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        output_path = work_dir / "result.tif"

        logger.info(
            "[flood %s] product=%s threshold=%s aoi=%s",
            job_id, product_zip, threshold_sigma0, aoi_bbox,
        )
        await _update_job(job_id, status="processing", progress=0, message="Starting SNAP…")
        await log.set_progress(0, "Starting SNAP…")

        def _fail_detail(tail: list[str]) -> str:
            salient = [ln for ln in tail if "NodeId" in ln or "Error" in ln or "Caused by" in ln]
            return " | ".join((salient or tail)[-6:]) or "no output produced"

        current_input = product_zip.as_posix()

        try:
            for stage_index, build_graph_name, step_tag in PREPROCESS_STEPS:
                build_graph = globals()[build_graph_name]
                output = work_dir / f"{stage_index}_{step_tag}.dim"
                graph_path = work_dir / f"stage{stage_index}_{step_tag}.xml"

                if stage_index == 4:  # Subset - the only stage that takes an AOI
                    graph_xml = build_graph(current_input, output.as_posix(), aoi_bbox)
                else:
                    graph_xml = build_graph(current_input, output.as_posix())
                graph_path.write_text(graph_xml, encoding="utf-8")

                ok, tail = await _run_gpt_stage(job_id, log, settings.snap_gpt_path, graph_path, stage_index)
                if not ok or not output.exists():
                    msg = f"SNAP failed at '{STAGE_NAMES[stage_index]}': {_fail_detail(tail)}"
                    await log.mark_failed(msg)
                    await _update_job(job_id, status="failed", message=msg)
                    return

                current_input = output.as_posix()

            mask_graph_path = work_dir / "stage7_mask.xml"
            mask_graph_path.write_text(
                build_flood_mask_graph(current_input, output_path.as_posix(), threshold_sigma0),
                encoding="utf-8",
            )
            ok, tail = await _run_gpt_stage(job_id, log, settings.snap_gpt_path, mask_graph_path, stage_index=7)
            if not ok or not output_path.exists():
                msg = f"SNAP failed at '{STAGE_MASK}': {_fail_detail(tail)}"
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
            stage=STAGE_MASK,
            stage_index=TOTAL_STAGES,
            message="Done",
            result_path=output_path.as_posix(),
        )
        await log.set_progress(100, "Flood mask ready")


def trigger_flood_job(
    job_id: uuid.UUID,
    satellite_id: uuid.UUID,
    threshold_sigma0: float,
    settings: Settings,
    aoi_bbox: list[float] | None = None,
) -> None:
    task = asyncio.create_task(
        run_flood_job(job_id, satellite_id, threshold_sigma0, settings, aoi_bbox)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
