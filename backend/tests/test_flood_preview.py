"""Unit tests for flood_preview.py's rasterio/numpy/Pillow RGBA compositing.

Uses real, tiny in-memory GeoTIFFs (written via rasterio) rather than mocking
GDAL subprocess calls - the whole point of this module is to stop depending
on GDAL's `gdaldem color-relief` interpolation semantics (which, without a
NoData tag on the source, painted an entire real result.tif solid red - a
live-confirmed production bug), so tests exercise the real read/composite/
save path against real pixel data instead."""
import zipfile
from io import BytesIO

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_bounds

from app.services import flood_preview


def _write_test_geotiff(path, band: np.ndarray, bounds=(97.0, 4.0, 98.0, 5.0)) -> None:
    west, south, east, north = bounds
    transform = from_bounds(west, south, east, north, band.shape[1], band.shape[0])
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=band.shape[0],
        width=band.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as ds:
        ds.write(band, 1)


async def test_ensure_preview_returns_none_when_result_tif_is_missing(tmp_path):
    bounds = await flood_preview.ensure_preview(tmp_path)

    assert bounds is None


async def test_ensure_preview_produces_transparent_background_and_opaque_red_flood(tmp_path):
    band = np.full((4, 4), np.nan, dtype="float32")
    band[1, 1] = 1.0
    band[2, 2] = 1.0
    _write_test_geotiff(tmp_path / "result.tif", band)

    bounds = await flood_preview.ensure_preview(tmp_path)

    assert bounds == [4.0, 97.0, 5.0, 98.0]  # south, west, north, east
    png = Image.open(tmp_path / "preview.png")
    assert png.mode == "RGBA"
    pixels = np.array(png)
    assert tuple(pixels[1, 1]) == (255, 0, 0, 180)
    assert tuple(pixels[2, 2]) == (255, 0, 0, 180)
    # Background (NaN in the source) must be fully transparent, not white/black/red.
    assert tuple(pixels[0, 0]) == (0, 0, 0, 0)
    assert tuple(pixels[3, 3]) == (0, 0, 0, 0)


async def test_ensure_preview_downsamples_to_max_dimension_without_blending_values(tmp_path):
    band = np.full((3000, 4000), np.nan, dtype="float32")
    band[10:20, 10:20] = 1.0
    _write_test_geotiff(tmp_path / "result.tif", band)

    await flood_preview.ensure_preview(tmp_path)

    png = Image.open(tmp_path / "preview.png")
    assert max(png.size) <= flood_preview._PREVIEW_MAX_DIMENSION
    pixels = np.array(png)
    # Nearest-neighbor resampling must only ever produce the two exact colors -
    # no blended/interpolated in-between RGBA values from downsampling.
    unique_colors = {tuple(c) for c in pixels.reshape(-1, 4)}
    assert unique_colors <= {(255, 0, 0, 180), (0, 0, 0, 0)}


async def test_ensure_preview_caches_and_does_not_recompute(tmp_path):
    band = np.full((4, 4), np.nan, dtype="float32")
    band[0, 0] = 1.0
    _write_test_geotiff(tmp_path / "result.tif", band)

    first = await flood_preview.ensure_preview(tmp_path)
    mtime_before = (tmp_path / "preview.png").stat().st_mtime_ns
    second = await flood_preview.ensure_preview(tmp_path)
    mtime_after = (tmp_path / "preview.png").stat().st_mtime_ns

    assert first == second == [4.0, 97.0, 5.0, 98.0]
    assert mtime_before == mtime_after


async def test_ensure_kmz_packages_doc_kml_and_rgba_png_no_tiff(tmp_path):
    band = np.full((4, 4), np.nan, dtype="float32")
    band[0, 0] = 1.0
    _write_test_geotiff(tmp_path / "result.tif", band)

    kmz_path = await flood_preview.ensure_kmz(tmp_path, name="Test Flood")

    assert kmz_path is not None
    with zipfile.ZipFile(kmz_path) as zf:
        names = zf.namelist()
        assert "doc.kml" in names
        assert "overlay.png" in names
        assert not any(n.lower().endswith((".tif", ".tiff")) for n in names)

        kml_content = zf.read("doc.kml").decode("utf-8")
        assert "<GroundOverlay>" in kml_content
        assert "<href>overlay.png</href>" in kml_content
        assert "Test Flood" in kml_content

        png_bytes = zf.read("overlay.png")
        img = Image.open(BytesIO(png_bytes))
        assert img.mode == "RGBA"
