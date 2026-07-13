"""Unit tests for flood.py's sequential (single-track) job orchestration.

Simpler than test_landslide.py's equivalent: there's no parallel pre/post
track or barrier-sync logic to test here, since Flood processes exactly one
product. Reuses landslide.py's already-tested _run_gpt_process_blocking/
_verify_snap_gpt directly (not re-tested here - see test_landslide.py for
their own coverage). _run_gpt_stage is flood-local (see module docstring in
flood.py): it must NOT be landslide's version, since landslide's STAGE_NAMES/
TOTAL_STAGES/_update_job are hardcoded to landslide's own 7-stage pipeline and
landslide_jobs table - calling landslide's _run_gpt_stage with flood's
stage_index=7 (its 8th and final stage) raises IndexError."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from app.services import flood


class FakeLog:
    def __init__(self) -> None:
        self.progress_calls: list[tuple[int, str]] = []
        self.failed_message: str | None = None

    async def set_progress(self, progress: int, description: str) -> None:
        self.progress_calls.append((progress, description))

    async def mark_failed(self, message: str) -> None:
        self.failed_message = message


def _activity_log_returning(log: FakeLog):
    @asynccontextmanager
    async def _fake_activity_log(**_kwargs):
        yield log

    return _fake_activity_log


def _make_recording_graph_builder(calls: list[tuple], output_index: int = 1):
    """Fake stand-in for one of flood_graph.build_*_graph: records the raw
    positional args it was called with, and creates an empty placeholder
    file at the output path so run_flood_job's own `.exists()` checks pass
    without needing real SNAP."""

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

    monkeypatch.setattr(flood, "_update_job", _fake_update_job)
    return calls


async def test_run_gpt_stage_handles_final_mask_stage_without_indexerror(monkeypatch, fake_update_job):
    """Regression test for the critical bug: flood.py used to import
    _run_gpt_stage from landslide.py instead of defining its own. Landslide's
    version indexes into landslide.STAGE_NAMES (only 7 entries, indices 0-6),
    so calling it for flood's stage_index=7 (the final Band Maths/mask stage,
    flood has 8 stages) raised IndexError - crashing every flood job on its
    last stage. flood._run_gpt_stage must be flood-local and use flood's own
    8-entry STAGE_NAMES/TOTAL_STAGES and flood's own _update_job
    (FloodJobRepository), not landslide's."""

    def fake_blocking(job_id, label, gpt_path, graph_path, report_progress):
        report_progress(50)
        report_progress(100)
        return True, ["done."]

    monkeypatch.setattr(flood, "_run_gpt_process_blocking", fake_blocking)
    log = FakeLog()

    ok, tail = await flood._run_gpt_stage(
        job_id="job-1", log=log, gpt_path="gpt", graph_path=Path("g.xml"), stage_index=7
    )
    await asyncio.sleep(0.05)

    assert ok is True
    assert tail == ["done."]

    # Progress updates must land on flood's own _update_job (patched by the
    # fake_update_job fixture below) with FLOOD's stage name/index - not
    # landslide's, and not silently no-op against the wrong table.
    stage_update_calls = [c for c in fake_update_job if "stage" in c]
    assert stage_update_calls, "expected at least one _update_job call carrying a stage field"
    assert stage_update_calls[0]["stage"] == flood.STAGE_MASK
    assert stage_update_calls[0]["stage_index"] == 7

    progress_update_calls = [c for c in fake_update_job if "progress" in c]
    assert progress_update_calls, "expected at least one _update_job call carrying a progress field"
    # TOTAL_STAGES=8, stage_index=7: overall = (7 + pct/100) / 8 * 100, capped at 99.
    # 50% -> (7.5/8)*100 = 93 ; 100% -> capped at 99 until the job confirms completion.
    assert [c["progress"] for c in progress_update_calls] == [93, 99]

    reported_overall = [progress for progress, _message in log.progress_calls]
    assert reported_overall == [93, 99]


def test_stage_names_and_total_stages_reflect_the_eight_stage_pipeline():
    assert flood.STAGE_NAMES == [
        "Thermal Noise Removal",
        "Apply Orbit File",
        "Remove GRD Border Noise",
        "Calibration",
        "Subset",
        "Speckle Filtering",
        "Terrain Correction",
        "Band Maths & mask export",
    ]
    assert flood.TOTAL_STAGES == 8


async def test_run_flood_job_chains_dim_outputs_and_gates_aoi_bbox_to_subset_stage(monkeypatch, tmp_path):
    monkeypatch.setattr(flood, "LANDSLIDE_STORAGE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(flood, "FLOOD_STORAGE_ROOT", tmp_path)

    async def fake_resolve_product_zip(satellite_id):
        return Path("input.zip")

    async def fake_verify_snap_gpt(gpt_path):
        return None

    log = FakeLog()
    monkeypatch.setattr(flood, "_resolve_product_zip", fake_resolve_product_zip)
    monkeypatch.setattr(flood, "_verify_snap_gpt", fake_verify_snap_gpt)
    monkeypatch.setattr(flood, "activity_log", _activity_log_returning(log))

    calls: list[tuple] = []
    for name in (
        "build_tnr_graph",
        "build_orbit_graph",
        "build_border_noise_graph",
        "build_calibration_graph",
        "build_speckle_graph",
        "build_terrain_correction_graph",
    ):
        monkeypatch.setattr(flood, name, _make_recording_graph_builder(calls, output_index=1))
    subset_calls: list[tuple] = []
    monkeypatch.setattr(flood, "build_subset_graph", _make_recording_graph_builder(subset_calls, output_index=1))
    mask_calls: list[tuple] = []
    monkeypatch.setattr(flood, "build_flood_mask_graph", _make_recording_graph_builder(mask_calls, output_index=1))

    change_ok = {"value": True}

    async def fake_run_gpt_stage(job_id, log, gpt_path, graph_path, stage_index):
        return change_ok["value"], ["done."]

    monkeypatch.setattr(flood, "_run_gpt_stage", fake_run_gpt_stage)

    await flood.run_flood_job(
        job_id="job-1",
        satellite_id="sat-1",
        threshold_sigma0=0.0137,
        settings=type("S", (), {"snap_gpt_path": "gpt"})(),
        aoi_bbox=[95.0, 4.0, 96.0, 5.0],
    )

    # Reassemble in true pipeline/chronological order: tnr, orbit, border, cal
    # (recorded into `calls`), then subset (recorded separately into
    # `subset_calls` so its AOI arg can be asserted on its own), then speckle,
    # tc (back in `calls`). A plain `calls + subset_calls` concatenation would
    # put subset's entry last instead of in its real position between cal and
    # speckle, breaking the chain assertion below despite a correct
    # implementation - splice it into the position it actually ran in.
    all_calls = calls[:4] + subset_calls + calls[4:]
    # 6 chained builders (tnr, orbit, border, cal, then subset separately, then
    # speckle, tc): each stage's output path becomes the next stage's input.
    assert all_calls[0][0] == "input.zip"  # tnr reads the original zip
    for i in range(1, len(all_calls)):
        assert all_calls[i][0] == all_calls[i - 1][1]

    # AOI reaches only the Subset stage.
    assert len(subset_calls[0]) == 3
    assert subset_calls[0][2] == [95.0, 4.0, 96.0, 5.0]
    for c in calls:
        assert len(c) == 2  # no other builder receives an aoi_bbox argument

    # Final mask stage receives the threshold and the last preprocessed .dim.
    assert mask_calls[0][0] == all_calls[-1][1]
    assert mask_calls[0][2] == 0.0137


async def test_run_flood_job_aborts_immediately_on_mid_pipeline_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(flood, "FLOOD_STORAGE_ROOT", tmp_path)

    async def fake_resolve_product_zip(satellite_id):
        return Path("input.zip")

    async def fake_verify_snap_gpt(gpt_path):
        return None

    log = FakeLog()
    monkeypatch.setattr(flood, "_resolve_product_zip", fake_resolve_product_zip)
    monkeypatch.setattr(flood, "_verify_snap_gpt", fake_verify_snap_gpt)
    monkeypatch.setattr(flood, "activity_log", _activity_log_returning(log))

    monkeypatch.setattr(flood, "build_tnr_graph", _make_recording_graph_builder([], output_index=1))
    monkeypatch.setattr(flood, "build_orbit_graph", _make_recording_graph_builder([], output_index=1))

    later_stage_calls: list[tuple] = []
    for name in (
        "build_border_noise_graph",
        "build_calibration_graph",
        "build_subset_graph",
        "build_speckle_graph",
        "build_terrain_correction_graph",
        "build_flood_mask_graph",
    ):
        monkeypatch.setattr(flood, name, _make_recording_graph_builder(later_stage_calls, output_index=1))

    stage_results = iter([(True, ["done."]), (False, ["Error: bad orbit file"])])

    async def fake_run_gpt_stage(job_id, log, gpt_path, graph_path, stage_index):
        return next(stage_results)

    monkeypatch.setattr(flood, "_run_gpt_stage", fake_run_gpt_stage)

    await flood.run_flood_job(
        job_id="job-1",
        satellite_id="sat-1",
        threshold_sigma0=0.0137,
        settings=type("S", (), {"snap_gpt_path": "gpt"})(),
        aoi_bbox=None,
    )

    assert later_stage_calls == []  # nothing past "Apply Orbit File" was ever attempted
    assert log.failed_message is not None
    assert "Apply Orbit File" in log.failed_message
