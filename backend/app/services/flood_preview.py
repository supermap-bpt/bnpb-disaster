"""Renders a flood-mask GeoTIFF into a web-map overlay PNG (and KMZ package)
by compositing pixel values directly with rasterio/numpy/Pillow, instead of
via the GDAL CLI's `gdaldem color-relief`.

Root cause of the "solid red box" bug this replaces: SNAP's Write operator
never propagates the Band Maths node's NaN nodata flag into the final
GeoTIFF's NoData tag (confirmed live: `gdalinfo` reports no NoData Value on
a real result.tif even though ~57% of its pixels are genuine NaN). Without a
NoData tag, `gdaldem color-relief` cannot tell flood pixels from background
and paints the entire raster with its only color-table entry. Reading the
raw pixel array and testing `np.isnan()` per pixel sidesteps this entirely -
it does not depend on the GeoTIFF's NoData metadata being set correctly.

flood.py's own SNAP Terrain-Correction stage always outputs WGS84(DD) (plain
lat/lon), so no reprojection step is needed here - result.tif's own bounds
are already the WGS84 [south, west, north, east] Leaflet/KML expects.
"""
import asyncio
import json
import logging
import os
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import rasterio

# This machine has other GIS tooling (e.g. SuperMap iDesktopX) that sets
# PROJ_LIB/GDAL_DATA globally in the Windows environment, pointing at an
# incompatible PROJ database version. Left as-is, any process that inherits
# these env vars (including this one) fails with
# "rasterio.errors.CRSError: The EPSG code is unknown... DATABASE.LAYOUT
# .VERSION.MINOR = 4 whereas a number >= 6 is expected" the moment a CRS is
# resolved - confirmed live. Force rasterio to use its own bundled GDAL/PROJ
# data instead, before any dataset is opened.
_rasterio_dir = Path(rasterio.__file__).parent
for _env_var, _bundled_dir in (("GDAL_DATA", "gdal_data"), ("PROJ_LIB", "proj_data"), ("PROJ_DATA", "proj_data")):
    _bundled_path = _rasterio_dir / _bundled_dir
    if _bundled_path.is_dir():
        os.environ[_env_var] = str(_bundled_path)
os.environ.pop("GDAL_DRIVER_PATH", None)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402
from rasterio.errors import RasterioIOError  # noqa: E402

logger = logging.getLogger(__name__)

# Cap the web-preview/KMZ overlay's long edge at this many pixels - a
# full-scene, high-resolution result.tif produces a PNG too large for a
# browser to decode at native resolution. result.tif itself (the actual
# download) stays full resolution.
_PREVIEW_MAX_DIMENSION = 2048

# Flood pixels (band value == 1) render opaque-ish red; everything else
# (genuine NaN background, per the Band Maths `else NaN` expression) stays
# fully transparent so the basemap shows through untouched.
_FLOOD_RGBA = (255, 0, 0, 180)


def _read_flood_rgba_blocking(tif_path: str) -> tuple[np.ndarray, list[float]] | None:
    try:
        with rasterio.open(tif_path) as ds:
            scale = min(1.0, _PREVIEW_MAX_DIMENSION / max(ds.width, ds.height))
            out_height = max(1, round(ds.height * scale))
            out_width = max(1, round(ds.width * scale))
            band = ds.read(1, out_shape=(out_height, out_width), resampling=Resampling.nearest)
            bounds = ds.bounds
    except RasterioIOError:
        logger.warning("Could not open result.tif at %s", tif_path)
        return None

    rgba = np.zeros((*band.shape, 4), dtype=np.uint8)
    rgba[band == 1] = _FLOOD_RGBA
    # Everything else (NaN background) is left at the zero-fill default,
    # i.e. fully transparent (0, 0, 0, 0) - never colored.
    return rgba, [bounds.bottom, bounds.left, bounds.top, bounds.right]


async def ensure_preview(work_dir: Path) -> list[float] | None:
    """Ensure ``preview.png`` + ``bounds.json`` exist for the result.tif in
    ``work_dir``. Returns WGS84 bounds ``[south, west, north, east]`` (Leaflet
    order-friendly) or None if there is no result or it could not be read.
    """
    result = work_dir / "result.tif"
    if not result.exists():
        return None

    png = work_dir / "preview.png"
    bounds_file = work_dir / "bounds.json"
    if png.exists() and bounds_file.exists():
        try:
            return json.loads(bounds_file.read_text())
        except (ValueError, OSError):
            pass  # regenerate on corrupt cache

    loop = asyncio.get_running_loop()
    outcome = await loop.run_in_executor(None, _read_flood_rgba_blocking, result.as_posix())
    if outcome is None:
        return None
    rgba, bounds = outcome

    def _save_png() -> None:
        Image.fromarray(rgba).save(png.as_posix())

    await loop.run_in_executor(None, _save_png)
    bounds_file.write_text(json.dumps(bounds), encoding="utf-8")
    return bounds


async def ensure_kmz(work_dir: Path, name: str = "Flood mask") -> Path | None:
    """Ensure ``result.kmz`` exists for the result in ``work_dir`` and return its
    path (or None). Packages the RGBA mask PNG as a KML GroundOverlay so it opens
    directly in Google Earth over the correct footprint, with only flood pixels
    opaque and everything else transparent."""
    kmz = work_dir / "result.kmz"
    if kmz.exists():
        return kmz

    bounds = await ensure_preview(work_dir)
    png = work_dir / "preview.png"
    if bounds is None or not png.exists():
        return None

    south, west, north, east = bounds
    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <GroundOverlay>
    <name>{escape(name)}</name>
    <Icon>
      <href>overlay.png</href>
    </Icon>
    <LatLonBox>
      <north>{north}</north>
      <south>{south}</south>
      <east>{east}</east>
      <west>{west}</west>
    </LatLonBox>
  </GroundOverlay>
</kml>
"""
    try:
        with zipfile.ZipFile(kmz, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.kml", kml)
            zf.write(png, "overlay.png")
    except OSError:
        logger.warning("Failed to write KMZ for %s", work_dir, exc_info=True)
        kmz.unlink(missing_ok=True)
        return None
    return kmz
