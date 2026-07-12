"""Unit tests for flood.py's sequential (single-track) job orchestration.

Simpler than test_landslide.py's equivalent: there's no parallel pre/post
track or barrier-sync logic to test here, since Flood processes exactly one
product. Reuses landslide.py's already-tested _run_gpt_stage/
_run_gpt_process_blocking/_verify_snap_gpt directly (not re-tested here -
see test_landslide.py for their own coverage)."""
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
