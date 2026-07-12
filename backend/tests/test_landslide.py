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

    async def set_progress(self, progress: int, description: str) -> None:
        self.progress_calls.append((progress, description))


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
    """With TOTAL_STAGES=2, stage_index=1 (change-detection) occupies the
    second half of the 0-100 bar: overall = (1 + pct/100) / 2 * 100. Runs via
    the real thread executor + asyncio.run_coroutine_threadsafe bridge."""

    def fake_blocking(job_id, label, gpt_path, graph_path, report_progress):
        report_progress(50)
        report_progress(100)
        return True, ["done."]

    monkeypatch.setattr(landslide, "_run_gpt_process_blocking", fake_blocking)
    log = FakeLog()

    from pathlib import Path

    ok, tail = await landslide._run_gpt_stage(
        job_id="job-1", log=log, gpt_path="gpt", graph_path=Path("g.xml"), stage_index=1
    )
    await asyncio.sleep(0.05)  # let cross-thread-scheduled progress callbacks flush

    assert ok is True
    assert tail == ["done."]
    reported_overall = [progress for progress, _message in log.progress_calls]
    # 50% -> (1 + 0.5)/2*100 = 75 ; 100% -> capped at 99 until the job confirms completion.
    assert reported_overall == [75, 99]


async def test_run_parallel_preprocess_reports_combined_average_progress(monkeypatch):
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

    pre_ok, pre_tail, post_ok, post_tail = await landslide._run_parallel_preprocess(
        job_id="job-1", log=log, gpt_path="gpt", pre_graph_path=Path("pre.xml"), post_graph_path=Path("post.xml")
    )
    await asyncio.sleep(0.05)

    assert (pre_ok, post_ok) == (True, True)
    assert pre_tail == ["pre-event done."]
    assert post_tail == ["post-event done."]
    # Both stages together occupy the first half (1/TOTAL_STAGES) of the bar;
    # final combined progress once both hit 100% is 100/100/2*100 = 50.
    final_overall = log.progress_calls[-1][0]
    assert final_overall == 50


async def test_run_parallel_preprocess_surfaces_a_single_sides_failure(monkeypatch):
    def fake_blocking(job_id, label, gpt_path, graph_path, report_progress):
        if label == "pre-event":
            return False, ["Error: bad orbit file"]
        report_progress(100)
        return True, ["done."]

    monkeypatch.setattr(landslide, "_run_gpt_process_blocking", fake_blocking)
    log = FakeLog()

    from pathlib import Path

    pre_ok, pre_tail, post_ok, post_tail = await landslide._run_parallel_preprocess(
        job_id="job-1", log=log, gpt_path="gpt", pre_graph_path=Path("pre.xml"), post_graph_path=Path("post.xml")
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


def test_stage_names_and_total_stages_reflect_the_two_stage_parallel_pipeline():
    assert landslide.STAGE_NAMES == [
        "Preprocess pre & post event (parallel)",
        "Collocate & change-detection mask",
    ]
    assert landslide.TOTAL_STAGES == 2
