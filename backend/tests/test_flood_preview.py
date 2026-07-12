"""Unit tests for flood_preview.py's GDAL subprocess layer - mirrors
test_landslide_preview.py's structure exactly (same root-cause thread-executor
regression test), adjusted for Flood's simpler single-value color table."""
from pathlib import Path

import pytest

from app.services import flood_preview


class FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


async def test_run_never_uses_asyncio_subprocess_exec(monkeypatch):
    def fail_if_called(*_a, **_k):
        raise AssertionError("must not use asyncio.create_subprocess_exec")

    monkeypatch.setattr(flood_preview.asyncio, "create_subprocess_exec", fail_if_called)
    monkeypatch.setattr(
        flood_preview.subprocess, "run", lambda args, capture_output: FakeCompletedProcess(0)
    )

    ok = await flood_preview._run("gdalwarp", "-t_srs", "EPSG:4326")

    assert ok is True


async def test_run_reports_nonzero_exit_as_not_ok(monkeypatch):
    monkeypatch.setattr(
        flood_preview.subprocess,
        "run",
        lambda args, capture_output: FakeCompletedProcess(1, stderr=b"Error: bad input"),
    )

    ok = await flood_preview._run("gdalwarp", "-t_srs", "EPSG:4326")

    assert ok is False


async def test_ensure_preview_returns_none_when_result_tif_is_missing(tmp_path):
    bounds = await flood_preview.ensure_preview(tmp_path)

    assert bounds is None


async def test_ensure_preview_caps_gdalwarp_output_and_uses_flood_color_table(monkeypatch, tmp_path):
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

    monkeypatch.setattr(flood_preview.subprocess, "run", fake_run)

    bounds = await flood_preview.ensure_preview(tmp_path)

    assert bounds == [4.0, 95.0, 5.0, 96.0]
    gdaldem_call = next(c for c in calls if c[0] == "gdaldem")
    assert "-b" in gdaldem_call
    band_index = gdaldem_call[gdaldem_call.index("-b") + 1]
    assert band_index == str(flood_preview._FLOOD_MASK_BAND)
    gdalwarp_call = next(c for c in calls if c[0] == "gdalwarp")
    assert "-ts" in gdalwarp_call
    ts_index = gdalwarp_call.index("-ts")
    assert gdalwarp_call[ts_index + 1] == str(flood_preview._PREVIEW_MAX_DIMENSION)
    assert gdalwarp_call[ts_index + 2] == "0"


def test_color_table_maps_flood_value_to_red_and_everything_else_transparent():
    lines = flood_preview._COLOR_TABLE.strip().splitlines()
    assert "1 255 0 0 255" in lines  # flood (value 1) -> opaque red
    assert "nv 0 0 0 0" in lines  # genuine no-data (the else-NaN branch) -> transparent
