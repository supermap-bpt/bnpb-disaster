"""Runs the SNAP landslide change-detection graph as a headless background job.

Modelled on ``product_file.cache_product_file``: an asyncio background task that
shells out to ESA SNAP's ``gpt``, streams progress into both the LandslideJob row
and an ActivityLog entry, and marks the job completed/failed at the end.

Windows subprocess note: every ``gpt`` invocation here runs via the classic
blocking ``subprocess`` module inside a thread-pool executor
(``loop.run_in_executor``), never ``asyncio.create_subprocess_exec``. On
Windows, uvicorn's own socket handling forces the event loop onto
``SelectorEventLoop``, and ``SelectorEventLoop`` cannot spawn subprocesses at
all (raises ``NotImplementedError`` - only ``ProactorEventLoop`` supports it).
Running subprocesses via a worker thread sidesteps this entirely and works
under either loop type.
"""
import asyncio
import logging
import re
import subprocess
import threading
import uuid
from pathlib import Path

from app.config import Settings
from app.db.landslide_repository import LandslideJobRepository
from app.db.repository import SatelliteRepository
from app.db.session import get_sessionmaker
from app.services.activity_log import activity_log
from app.services.snap_graph import (
    build_calibration_graph,
    build_change_detection_graph,
    build_db_graph,
    build_orbit_graph,
    build_speckle_graph,
    build_terrain_correction_graph,
    build_tnr_graph,
)

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


def _run_subprocess_capture(args: list[str]) -> tuple[bool, str]:
    """Blocking: runs `args`, returns (found, combined stdout+stderr text). Used
    via loop.run_in_executor - see the module docstring's "Windows subprocess
    note" for why this can't use asyncio.create_subprocess_exec directly."""
    try:
        result = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError:
        return False, ""
    return True, (result.stdout or "") + (result.stderr or "")


async def _verify_snap_gpt(gpt_path: str) -> str | None:
    """Return an error message if `gpt_path` is missing or is not ESA SNAP's gpt
    (e.g. macOS' /usr/sbin/gpt partition tool, which would misread the graph
    file as a subcommand), else None."""
    loop = asyncio.get_running_loop()
    found, text = await loop.run_in_executor(None, _run_subprocess_capture, [gpt_path, "-h"])
    if not found:
        return f"SNAP gpt not found at '{gpt_path}'. {_GPT_INSTALL_HINT}"
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


# Ordered pipeline stages shown in the UI stepper. Keep in sync with TOTAL_STAGES,
# db/models.py's LandslideJob.total_stages default, and the frontend
# LANDSLIDE_STAGE_KEYS labels. Each of the 6 preprocessing operators runs pre
# and post concurrently (they're independent per operator, until Collocate),
# barrier-synced at each operator boundary - see _run_parallel_step.
STAGE_ORBIT = "Apply Orbit File"
STAGE_TNR = "Thermal Noise Removal"
STAGE_CALIBRATION = "Calibration"
STAGE_SPECKLE = "Speckle Filtering"
STAGE_TERRAIN_CORRECTION = "Terrain Correction"
STAGE_DB = "Linear to dB"
STAGE_CHANGE_DETECTION = "Collocate & change-detection mask"
STAGE_NAMES = [
    STAGE_ORBIT,
    STAGE_TNR,
    STAGE_CALIBRATION,
    STAGE_SPECKLE,
    STAGE_TERRAIN_CORRECTION,
    STAGE_DB,
    STAGE_CHANGE_DETECTION,
]
TOTAL_STAGES = len(STAGE_NAMES)

# (stage_index, graph_builder, filename tag) for each of the 6 preprocessing
# operators, in order. graph_builder(source, output_dim) -> graph XML, except
# stage 0 (orbit) which also takes the optional aoi_bbox - see run_landslide_job.
PREPROCESS_STEPS = [
    (0, build_orbit_graph, "orbit"),
    (1, build_tnr_graph, "tnr"),
    (2, build_calibration_graph, "cal"),
    (3, build_speckle_graph, "speckle"),
    (4, build_terrain_correction_graph, "tc"),
    (5, build_db_graph, "db"),
]


def _run_gpt_process_blocking(
    job_id: uuid.UUID, label: str, gpt_path: str, graph_path: Path, report_progress
) -> tuple[bool, list[str]]:
    """Blocking: runs one gpt graph to completion via the classic `subprocess`
    module (see the module docstring's Windows subprocess note), parsing "NN%"
    progress markers and calling `report_progress(pct)` (a plain sync callable -
    this runs on a worker thread, not the event loop) for each. Returns
    (exited_zero, last_40_lines). Python's logging module is thread-safe, so
    logging directly from this worker-thread function is safe.

    gpt streams its progress bar as dots ("....10%....20%") on a SINGLE line with
    no newline until "done.", so a line-buffered reader would block - read raw
    byte chunks instead."""
    process = subprocess.Popen(
        [gpt_path, graph_path.as_posix(), "-q", "4"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    tail: list[str] = []
    buffer = b""
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(512)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            raw_line, buffer = buffer.split(b"\n", 1)
            line = raw_line.decode(errors="replace").rstrip()
            if line:
                logger.info("[landslide %s] %s: %s", job_id, label, line)
                tail.append(line)
                del tail[:-40]
        matches = _PROGRESS_RE.findall(chunk)
        if matches:
            report_progress(min(int(matches[-1]), 100))

    return_code = process.wait()
    logger.info("[landslide %s] %s exited with code %s", job_id, label, return_code)
    return return_code == 0, tail


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
    logger.info("[landslide %s] stage %s exited ok=%s", job_id, stage_index + 1, ok)
    return ok, tail


async def _run_parallel_step(
    job_id: uuid.UUID,
    log,
    gpt_path: str,
    stage_index: int,
    pre_graph_path: Path,
    post_graph_path: Path,
) -> tuple[bool, list[str], bool, list[str]]:
    """Runs one operator's pre-event and post-event graphs as two concurrent
    gpt subprocesses (they're independent within this operator) instead of one
    after another. Returns (pre_ok, pre_tail, post_ok, post_tail)."""
    stage_name = STAGE_NAMES[stage_index]
    await _update_job(
        job_id, status="processing", stage=stage_name, stage_index=stage_index, message=f"{stage_name}…"
    )
    logger.info("[landslide %s] stage %s/%s: %s", job_id, stage_index + 1, TOTAL_STAGES, stage_name)

    loop = asyncio.get_running_loop()
    pcts = {"pre": 0, "post": 0}
    last_reported = -1
    lock = threading.Lock()

    def make_reporter(which: str):
        def report_progress(pct: int) -> None:
            # Called from one of the two executor worker threads below - both
            # threads share `pcts`/`last_reported`, hence the lock.
            nonlocal last_reported
            with lock:
                pcts[which] = pct
                combined = (pcts["pre"] + pcts["post"]) / 2
                overall = min(int((stage_index + combined / 100) / TOTAL_STAGES * 100), 99)
                should_post = overall >= last_reported + 2
                if should_post:
                    last_reported = overall
                    message = f"{stage_name}… pre {pcts['pre']}% / post {pcts['post']}%"
            if should_post:

                async def _post() -> None:
                    await _update_job(job_id, progress=overall, message=message)
                    await log.set_progress(overall, message)

                asyncio.run_coroutine_threadsafe(_post(), loop)

        return report_progress

    (pre_ok, pre_tail), (post_ok, post_tail) = await asyncio.gather(
        loop.run_in_executor(
            None,
            _run_gpt_process_blocking,
            job_id,
            "pre-event",
            gpt_path,
            pre_graph_path,
            make_reporter("pre"),
        ),
        loop.run_in_executor(
            None,
            _run_gpt_process_blocking,
            job_id,
            "post-event",
            gpt_path,
            post_graph_path,
            make_reporter("post"),
        ),
    )
    logger.info(
        "[landslide %s] stage %s exited pre_ok=%s post_ok=%s", job_id, stage_index + 1, pre_ok, post_ok
    )
    return pre_ok, pre_tail, post_ok, post_tail


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
        output_path = work_dir / "result.tif"

        logger.info(
            "[landslide %s] pre=%s post=%s threshold=%s aoi=%s",
            job_id, pre_zip, post_zip, threshold_db, aoi_bbox,
        )
        await _update_job(job_id, status="processing", progress=0, message="Starting SNAP…")
        await log.set_progress(0, "Starting SNAP…")

        def _fail_detail(tail: list[str]) -> str:
            salient = [ln for ln in tail if "NodeId" in ln or "Error" in ln or "Caused by" in ln]
            return " | ".join((salient or tail)[-6:]) or "no output produced"

        pre_input = pre_zip.as_posix()
        post_input = post_zip.as_posix()

        try:
            for stage_index, build_graph, step_tag in PREPROCESS_STEPS:
                pre_output = work_dir / f"pre_{stage_index}_{step_tag}.dim"
                post_output = work_dir / f"post_{stage_index}_{step_tag}.dim"
                pre_graph_path = work_dir / f"stage{stage_index}_pre_{step_tag}.xml"
                post_graph_path = work_dir / f"stage{stage_index}_post_{step_tag}.xml"

                if stage_index == 0:
                    pre_graph_xml = build_graph(pre_input, pre_output.as_posix(), aoi_bbox)
                    post_graph_xml = build_graph(post_input, post_output.as_posix(), aoi_bbox)
                else:
                    pre_graph_xml = build_graph(pre_input, pre_output.as_posix())
                    post_graph_xml = build_graph(post_input, post_output.as_posix())
                pre_graph_path.write_text(pre_graph_xml, encoding="utf-8")
                post_graph_path.write_text(post_graph_xml, encoding="utf-8")

                pre_ok, pre_tail, post_ok, post_tail = await _run_parallel_step(
                    job_id, log, settings.snap_gpt_path, stage_index, pre_graph_path, post_graph_path
                )
                failures = []
                if not pre_ok or not pre_output.exists():
                    failures.append(f"pre-event: {_fail_detail(pre_tail)}")
                if not post_ok or not post_output.exists():
                    failures.append(f"post-event: {_fail_detail(post_tail)}")
                if failures:
                    msg = f"SNAP failed at '{STAGE_NAMES[stage_index]}': {' | '.join(failures)}"
                    await log.mark_failed(msg)
                    await _update_job(job_id, status="failed", message=msg)
                    return

                pre_input = pre_output.as_posix()
                post_input = post_output.as_posix()

            pre_dim = pre_input
            post_dim = post_input
            change_graph_path = work_dir / "stage6_change.xml"
            change_graph_path.write_text(
                build_change_detection_graph(
                    pre_dim,
                    post_dim,
                    output_path.as_posix(),
                    threshold_db,
                    settings.landslide_water_threshold_db,
                ),
                encoding="utf-8",
            )
            ok, tail = await _run_gpt_stage(job_id, log, settings.snap_gpt_path, change_graph_path, stage_index=6)
            if not ok or not output_path.exists():
                msg = f"SNAP failed at '{STAGE_CHANGE_DETECTION}': {_fail_detail(tail)}"
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
