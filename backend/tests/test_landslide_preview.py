"""Unit tests for landslide_preview.py's GDAL subprocess layer.

Root-cause regression: must never use asyncio.create_subprocess_exec (raises
NotImplementedError under uvicorn's forced SelectorEventLoop on Windows) -
only the blocking `subprocess` module via a thread executor. See
landslide.py's module docstring / test_landslide.py's equivalent test for the
same root cause fixed there first.
"""
from pathlib import Path

import pytest

from app.services import landslide_preview


class FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


async def test_run_never_uses_asyncio_subprocess_exec(monkeypatch):
    def fail_if_called(*_a, **_k):
        raise AssertionError("must not use asyncio.create_subprocess_exec")

    monkeypatch.setattr(landslide_preview.asyncio, "create_subprocess_exec", fail_if_called)
    monkeypatch.setattr(
        landslide_preview.subprocess, "run", lambda args, capture_output: FakeCompletedProcess(0)
    )

    ok = await landslide_preview._run("gdalwarp", "-t_srs", "EPSG:4326")

    assert ok is True


async def test_run_reports_nonzero_exit_as_not_ok(monkeypatch):
    monkeypatch.setattr(
        landslide_preview.subprocess,
        "run",
        lambda args, capture_output: FakeCompletedProcess(1, stderr=b"Error: bad input"),
    )

    ok = await landslide_preview._run("gdalwarp", "-t_srs", "EPSG:4326")

    assert ok is False


async def test_run_reports_missing_binary_as_not_ok(monkeypatch):
    def raise_not_found(args, capture_output):
        raise FileNotFoundError()

    monkeypatch.setattr(landslide_preview.subprocess, "run", raise_not_found)

    ok = await landslide_preview._run("gdalwarp")

    assert ok is False


async def test_wgs84_bounds_never_uses_asyncio_subprocess_exec(monkeypatch):
    def fail_if_called(*_a, **_k):
        raise AssertionError("must not use asyncio.create_subprocess_exec")

    monkeypatch.setattr(landslide_preview.asyncio, "create_subprocess_exec", fail_if_called)
    gdalinfo_json = (
        b'{"cornerCoordinates": {"upperLeft": [95.0, 5.0], "lowerRight": [96.0, 4.0]}}'
    )
    monkeypatch.setattr(
        landslide_preview.subprocess,
        "run",
        lambda args, capture_output: FakeCompletedProcess(0, stdout=gdalinfo_json),
    )

    bounds = await landslide_preview._wgs84_bounds(Path("wgs.tif"))

    assert bounds == [4.0, 95.0, 5.0, 96.0]  # [south, west, north, east]


async def test_wgs84_bounds_returns_none_on_gdalinfo_failure(monkeypatch):
    monkeypatch.setattr(
        landslide_preview.subprocess, "run", lambda args, capture_output: FakeCompletedProcess(1)
    )

    bounds = await landslide_preview._wgs84_bounds(Path("wgs.tif"))

    assert bounds is None


async def test_ensure_preview_returns_none_when_result_tif_is_missing(tmp_path):
    bounds = await landslide_preview.ensure_preview(tmp_path)

    assert bounds is None


async def test_ensure_preview_caps_gdalwarp_output_to_max_dimension(monkeypatch, tmp_path):
    """Regression test: a full, no-AOI scene's result.tif can be tens of
    thousands of pixels per side - without capping the reprojected output
    size, the preview PNG becomes too large for a browser to load/render.
    gdalwarp's `-ts <width> 0` sets an exact target width with the height
    auto-computed to preserve aspect ratio."""
    (tmp_path / "result.tif").write_bytes(b"fake")
    calls: list[tuple] = []

    def fake_run(args, capture_output):
        calls.append(tuple(args))
        if args[0] == "gdalinfo":
            return FakeCompletedProcess(
                0,
                stdout=b'{"cornerCoordinates": {"upperLeft": [95.0, 5.0], "lowerRight": [96.0, 4.0]}}',
            )
        return FakeCompletedProcess(0)

    monkeypatch.setattr(landslide_preview.subprocess, "run", fake_run)

    bounds = await landslide_preview.ensure_preview(tmp_path)

    assert bounds == [4.0, 95.0, 5.0, 96.0]
    gdalwarp_call = next(c for c in calls if c[0] == "gdalwarp")
    assert "-ts" in gdalwarp_call
    ts_index = gdalwarp_call.index("-ts")
    assert gdalwarp_call[ts_index + 1] == str(landslide_preview._PREVIEW_MAX_DIMENSION)
    assert gdalwarp_call[ts_index + 2] == "0"
