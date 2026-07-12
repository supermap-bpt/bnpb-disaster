"""Unit tests for the landslide gpt-subprocess/progress logic.

All `gpt` invocations run via loop.run_in_executor + the classic `subprocess`
module (never asyncio.create_subprocess_exec) - see landslide.py's module
docstring. That's a real root-cause fix, not incidental: on Windows, uvicorn
forces SelectorEventLoop, which cannot spawn subprocesses at all
(NotImplementedError). These tests fake subprocess.Popen (for
_run_gpt_process_blocking itself) or fake _run_gpt_process_blocking directly
(for the orchestration functions), and - since run_in_executor genuinely runs
work on separate OS threads - exercise the real cross-thread progress
callback bridging (asyncio.run_coroutine_threadsafe), not a mocked stand-in
for it.
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import landslide


class FakePopen:
    """Stands in for subprocess.Popen. `stdout` is `self` (both expose a sync
    `read`)."""

    def __init__(self, chunks: list[bytes], returncode: int = 0) -> None:
        self._chunks = list(chunks)
        self.returncode = returncode
        self.stdout = self

    def read(self, _n: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def wait(self) -> int:
        return self.returncode


class FakeLog:
    def __init__(self) -> None:
        self.progress_calls: list[tuple[int, str]] = []
        self.failed_message: str | None = None

    async def set_progress(self, progress: int, description: str) -> None:
        self.progress_calls.append((progress, description))

    async def mark_failed(self, message: str) -> None:
        self.failed_message = message


def _activity_log_returning(log: FakeLog):
    """Builds a fake replacement for `landslide.activity_log` (normally an
    `@asynccontextmanager` factory) that always yields `log`, so
    run_landslide_job-level tests don't need a real ActivityLog DB row."""

    @asynccontextmanager
    async def _fake_activity_log(**_kwargs):
        yield log

    return _fake_activity_log


def _make_recording_graph_builder(calls: list[tuple], output_index: int = 1):
    """Fake stand-in for one of the snap_graph.build_*_graph functions: records
    the raw positional args it was called with (so tests can check which
    stages get an aoi_bbox and how outputs chain into the next stage's input),
    and - since run_landslide_job checks `output.exists()` right after each
    stage - creates an empty placeholder file at the output path (args[output_index])
    so those checks pass without needing real SNAP to produce it."""

    def _fake(*args):
        calls.append(args)
        output = Path(args[output_index])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("")
        return "<graph/>"

    return _fake


@pytest.fixture(autouse=True)
def fake_update_job(monkeypatch):
    calls: list[dict] = []

    async def _fake_update_job(job_id, **fields):
        calls.append(fields)

    monkeypatch.setattr(landslide, "_update_job", _fake_update_job)
    return calls


async def test_run_gpt_process_blocking_parses_progress_and_collects_tail(monkeypatch):
    monkeypatch.setattr(
        landslide.subprocess,
        "Popen",
        lambda *a, **k: FakePopen([b"....10%....", b"55%..\ndone.\n"], returncode=0),
    )
    reported: list[int] = []

    ok, tail = landslide._run_gpt_process_blocking(
        "job-1", "test", "gpt", __import__("pathlib").Path("g.xml"), reported.append
    )

    assert ok is True
    assert reported == [10, 55]
    assert tail == ["....10%....55%..", "done."]


async def test_run_gpt_process_blocking_reports_nonzero_exit_as_not_ok(monkeypatch):
    monkeypatch.setattr(
        landslide.subprocess, "Popen", lambda *a, **k: FakePopen([b"Error: boom\n"], returncode=1)
    )

    ok, tail = landslide._run_gpt_process_blocking(
        "job-1", "test", "gpt", __import__("pathlib").Path("g.xml"), lambda _pct: None
    )

    assert ok is False
    assert tail == ["Error: boom"]


async def test_run_gpt_stage_scales_progress_into_its_slice_of_the_overall_bar(monkeypatch):
    """With TOTAL_STAGES=7, stage_index=6 (change-detection, the last stage)
    occupies the final 1/7 of the 0-100 bar: overall = (6 + pct/100) / 7 * 100."""

    def fake_blocking(job_id, label, gpt_path, graph_path, report_progress):
        report_progress(50)
        report_progress(100)
        return True, ["done."]

    monkeypatch.setattr(landslide, "_run_gpt_process_blocking", fake_blocking)
    log = FakeLog()

    from pathlib import Path

    ok, tail = await landslide._run_gpt_stage(
        job_id="job-1", log=log, gpt_path="gpt", graph_path=Path("g.xml"), stage_index=6
    )
    await asyncio.sleep(0.05)

    assert ok is True
    assert tail == ["done."]
    reported_overall = [progress for progress, _message in log.progress_calls]
    # 50% -> (6 + 0.5)/7*100 = 92 ; 100% -> capped at 99 until the job confirms completion.
    assert reported_overall == [92, 99]


async def test_run_parallel_step_reports_combined_average_progress_scaled_by_stage_index(monkeypatch):
    """stage_index=2 of 7 total: once both sides hit 100%, combined progress
    is (2 + 1.0) / 7 * 100 = 42 (not 50 - it's no longer stage 0 of 2)."""

    def fake_blocking(job_id, label, gpt_path, graph_path, report_progress):
        if label == "pre-event":
            report_progress(100)
        else:
            report_progress(50)
            report_progress(100)
        return True, [f"{label} done."]

    monkeypatch.setattr(landslide, "_run_gpt_process_blocking", fake_blocking)
    log = FakeLog()

    from pathlib import Path

    pre_ok, pre_tail, post_ok, post_tail = await landslide._run_parallel_step(
        job_id="job-1",
        log=log,
        gpt_path="gpt",
        stage_index=2,
        pre_graph_path=Path("pre.xml"),
        post_graph_path=Path("post.xml"),
    )
    await asyncio.sleep(0.05)

    assert (pre_ok, post_ok) == (True, True)
    assert pre_tail == ["pre-event done."]
    assert post_tail == ["post-event done."]
    final_overall = log.progress_calls[-1][0]
    assert final_overall == 42  # int((2 + 1.0) / 7 * 100) == 42


async def test_run_parallel_step_surfaces_a_single_sides_failure(monkeypatch):
    def fake_blocking(job_id, label, gpt_path, graph_path, report_progress):
        if label == "pre-event":
            return False, ["Error: bad orbit file"]
        report_progress(100)
        return True, ["done."]

    monkeypatch.setattr(landslide, "_run_gpt_process_blocking", fake_blocking)
    log = FakeLog()

    from pathlib import Path

    pre_ok, pre_tail, post_ok, post_tail = await landslide._run_parallel_step(
        job_id="job-1",
        log=log,
        gpt_path="gpt",
        stage_index=0,
        pre_graph_path=Path("pre.xml"),
        post_graph_path=Path("post.xml"),
    )

    assert pre_ok is False
    assert pre_tail == ["Error: bad orbit file"]
    assert post_ok is True


async def test_verify_snap_gpt_runs_via_executor_not_asyncio_subprocess(monkeypatch):
    """Root-cause regression test: must never call asyncio.create_subprocess_exec
    (raises NotImplementedError under uvicorn's forced SelectorEventLoop on
    Windows) - only the blocking `subprocess` module via an executor."""

    def fail_if_called(*_a, **_k):
        raise AssertionError("must not use asyncio.create_subprocess_exec")

    monkeypatch.setattr(landslide.asyncio, "create_subprocess_exec", fail_if_called)
    monkeypatch.setattr(
        landslide.subprocess,
        "run",
        lambda args, capture_output, text: type(
            "R", (), {"stdout": "SNAP Graph Processing Tool\ngpt <op>|<graph-file>", "stderr": ""}
        )(),
    )

    error = await landslide._verify_snap_gpt("gpt")

    assert error is None


async def test_verify_snap_gpt_reports_missing_binary(monkeypatch):
    def raise_not_found(args, capture_output, text):
        raise FileNotFoundError()

    monkeypatch.setattr(landslide.subprocess, "run", raise_not_found)

    error = await landslide._verify_snap_gpt("nonexistent-gpt")

    assert error is not None
    assert "not found" in error


def test_stage_names_and_total_stages_reflect_the_seven_stage_per_operator_pipeline():
    assert landslide.STAGE_NAMES == [
        "Apply Orbit File",
        "Thermal Noise Removal",
        "Calibration",
        "Speckle Filtering",
        "Terrain Correction",
        "Linear to dB",
        "Collocate & change-detection mask",
    ]
    assert landslide.TOTAL_STAGES == 7


class _RunLandslideJobFixture:
    """Shared monkeypatch scaffolding for run_landslide_job-level tests: fakes
    every operator's graph builder (recording call args) plus _resolve_product_zip,
    _verify_snap_gpt and activity_log, so the 6-step PREPROCESS_STEPS loop plus the
    final change-detection stage can run end-to-end without real SNAP or a real
    Postgres session. `_run_parallel_step` and `_run_gpt_stage` are left to the
    caller to monkeypatch, since that's what differs between the "everything
    succeeds" and "mid-pipeline failure" tests."""

    def __init__(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(landslide, "LANDSLIDE_STORAGE_ROOT", tmp_path)

        self.pre_zip = tmp_path / "pre.SAFE.zip"
        self.post_zip = tmp_path / "post.SAFE.zip"

        async def fake_resolve(satellite_id):
            return self.pre_zip if satellite_id == "pre-sat" else self.post_zip

        monkeypatch.setattr(landslide, "_resolve_product_zip", fake_resolve)

        async def fake_verify(gpt_path):
            return None

        monkeypatch.setattr(landslide, "_verify_snap_gpt", fake_verify)

        self.log = FakeLog()
        monkeypatch.setattr(landslide, "activity_log", _activity_log_returning(self.log))

        self.orbit_calls: list[tuple] = []
        self.tnr_calls: list[tuple] = []
        self.cal_calls: list[tuple] = []
        self.speckle_calls: list[tuple] = []
        self.tc_calls: list[tuple] = []
        self.db_calls: list[tuple] = []
        self.change_calls: list[tuple] = []

        # NOTE: run_landslide_job's loop iterates `landslide.PREPROCESS_STEPS`,
        # a module-level list built at import time from *direct references* to
        # build_orbit_graph/build_tnr_graph/etc - not attribute lookups. So
        # monkeypatching e.g. `landslide.build_orbit_graph` would NOT affect
        # what the loop actually calls; PREPROCESS_STEPS itself must be
        # monkeypatched. (build_change_detection_graph is different: it's
        # called by bare name directly in run_landslide_job's body, resolved
        # against module globals on every call, so patching the module
        # attribute works for it.)
        monkeypatch.setattr(
            landslide,
            "PREPROCESS_STEPS",
            [
                (0, _make_recording_graph_builder(self.orbit_calls), "orbit"),
                (1, _make_recording_graph_builder(self.tnr_calls), "tnr"),
                (2, _make_recording_graph_builder(self.cal_calls), "cal"),
                (3, _make_recording_graph_builder(self.speckle_calls), "speckle"),
                (4, _make_recording_graph_builder(self.tc_calls), "tc"),
                (5, _make_recording_graph_builder(self.db_calls), "db"),
            ],
        )
        monkeypatch.setattr(
            landslide,
            "build_change_detection_graph",
            _make_recording_graph_builder(self.change_calls, output_index=2),
        )

        self.settings = SimpleNamespace(snap_gpt_path="gpt", landslide_water_threshold_db=-17.0)

    async def run(self, aoi_bbox=None):
        await landslide.run_landslide_job(
            job_id="job-1",
            pre_satellite_id="pre-sat",
            post_satellite_id="post-sat",
            threshold_db=-2.0,
            settings=self.settings,
            aoi_bbox=aoi_bbox,
        )


async def test_run_landslide_job_chains_dim_outputs_and_gates_aoi_bbox_to_stage_zero(
    monkeypatch, tmp_path, fake_update_job
):
    fixture = _RunLandslideJobFixture(monkeypatch, tmp_path)

    parallel_step_calls: list[int] = []

    async def fake_run_parallel_step(job_id, log_, gpt_path, stage_index, pre_graph_path, post_graph_path):
        parallel_step_calls.append(stage_index)
        return True, [], True, []

    monkeypatch.setattr(landslide, "_run_parallel_step", fake_run_parallel_step)

    async def fake_run_gpt_stage(job_id, log_, gpt_path, graph_path, stage_index):
        return True, []

    monkeypatch.setattr(landslide, "_run_gpt_stage", fake_run_gpt_stage)

    await fixture.run(aoi_bbox=[1.0, 2.0, 3.0, 4.0])

    # All 6 preprocessing operators ran, in order, barrier-synced pre/post each time.
    assert parallel_step_calls == [0, 1, 2, 3, 4, 5]

    # Only stage 0 (orbit) receives the aoi_bbox; every other operator gets a
    # plain (source, output_dim) call with no third argument at all.
    assert len(fixture.orbit_calls) == 2
    for call in fixture.orbit_calls:
        assert len(call) == 3
        assert call[2] == [1.0, 2.0, 3.0, 4.0]

    for calls in (
        fixture.tnr_calls,
        fixture.cal_calls,
        fixture.speckle_calls,
        fixture.tc_calls,
        fixture.db_calls,
    ):
        assert len(calls) == 2
        for call in calls:
            assert len(call) == 2

    # Each stage's .dim output threads into the next stage's Read input, for the
    # pre-event and post-event tracks independently.
    orbit_pre, orbit_post = fixture.orbit_calls
    tnr_pre, tnr_post = fixture.tnr_calls
    cal_pre, cal_post = fixture.cal_calls
    speckle_pre, speckle_post = fixture.speckle_calls
    tc_pre, tc_post = fixture.tc_calls
    db_pre, db_post = fixture.db_calls

    assert orbit_pre[0] == fixture.pre_zip.as_posix()
    assert orbit_post[0] == fixture.post_zip.as_posix()
    assert tnr_pre[0] == orbit_pre[1]
    assert tnr_post[0] == orbit_post[1]
    assert cal_pre[0] == tnr_pre[1]
    assert cal_post[0] == tnr_post[1]
    assert speckle_pre[0] == cal_pre[1]
    assert speckle_post[0] == cal_post[1]
    assert tc_pre[0] == speckle_pre[1]
    assert tc_post[0] == speckle_post[1]
    assert db_pre[0] == tc_pre[1]
    assert db_post[0] == tc_post[1]

    # The final change-detection stage consumes both tracks' last .dim output.
    assert len(fixture.change_calls) == 1
    change_args = fixture.change_calls[0]
    assert change_args[0] == db_pre[1]
    assert change_args[1] == db_post[1]

    statuses = [fields.get("status") for fields in fake_update_job if "status" in fields]
    assert statuses[-1] == "completed"


async def test_run_landslide_job_aborts_immediately_on_mid_pipeline_failure(
    monkeypatch, tmp_path, fake_update_job
):
    fixture = _RunLandslideJobFixture(monkeypatch, tmp_path)

    parallel_step_calls: list[int] = []

    async def fake_run_parallel_step(job_id, log_, gpt_path, stage_index, pre_graph_path, post_graph_path):
        parallel_step_calls.append(stage_index)
        if stage_index == 2:  # Calibration fails.
            return False, ["Error: calibration boom"], True, ["post-event done."]
        return True, [], True, []

    monkeypatch.setattr(landslide, "_run_parallel_step", fake_run_parallel_step)

    change_detection_ran = False

    async def fake_run_gpt_stage(job_id, log_, gpt_path, graph_path, stage_index):
        nonlocal change_detection_ran
        change_detection_ran = True
        return True, []

    monkeypatch.setattr(landslide, "_run_gpt_stage", fake_run_gpt_stage)

    await fixture.run()

    # The loop stopped right after the failing stage - it never attempted the
    # later operators or the final change-detection stage.
    assert parallel_step_calls == [0, 1, 2]
    assert fixture.speckle_calls == []
    assert fixture.tc_calls == []
    assert fixture.db_calls == []
    assert fixture.change_calls == []
    assert change_detection_ran is False

    assert fixture.log.failed_message is not None
    assert "Calibration" in fixture.log.failed_message

    statuses = [fields.get("status") for fields in fake_update_job if "status" in fields]
    assert statuses[-1] == "failed"
