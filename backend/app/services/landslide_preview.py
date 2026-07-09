"""Renders a landslide-mask GeoTIFF into a web-map overlay PNG using the GDAL CLI.

The result.tif is a UTM multi-band product; band 5 is ``mask_combined`` (1 =
landslide candidate, 0 = background). This colourises that band (1 -> red, 0 /
no-data -> transparent), reprojects to WGS84, and emits a PNG plus the WGS84
bounds so the frontend can drop it on Leaflet as an ImageOverlay.

No Python raster deps (rasterio/GDAL bindings aren't installed) - shells out to
gdaldem/gdalwarp/gdal_translate/gdalinfo, which are on PATH.
"""
import asyncio
import json
import logging
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

# Band index (1-based) of mask_combined in result.tif: diff_VV, diff_VH, mask_VV,
# mask_VH, mask_combined.
_MASK_COMBINED_BAND = 5

# Landslide pixels -> dark magenta (stands out against green/tan terrain and is
# darker/more saturated than plain red); background & no-data -> transparent.
_COLOR_TABLE = "0 0 0 0 0\n1 139 0 139 255\nnv 0 0 0 0\n"


async def _run(*args: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except FileNotFoundError:
        logger.warning("GDAL tool not found: %s", args[0])
        return False
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("GDAL %s failed: %s", args[0], out.decode(errors="replace")[-500:])
        return False
    return True


async def ensure_preview(work_dir: Path) -> list[float] | None:
    """Ensure ``preview.png`` + ``bounds.json`` exist for the result.tif in
    ``work_dir``. Returns WGS84 bounds ``[south, west, north, east]`` (Leaflet
    order-friendly) or None if there is no result or GDAL is unavailable.
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

    color_file = work_dir / "_color.txt"
    rgba = work_dir / "_rgba.tif"
    wgs = work_dir / "_wgs.tif"
    color_file.write_text(_COLOR_TABLE, encoding="utf-8")

    ok = await _run(
        "gdaldem", "color-relief", "-alpha", "-b", str(_MASK_COMBINED_BAND),
        result.as_posix(), color_file.as_posix(), rgba.as_posix(),
    )
    ok = ok and await _run("gdalwarp", "-t_srs", "EPSG:4326", "-r", "near",
                           "-overwrite", rgba.as_posix(), wgs.as_posix())
    ok = ok and await _run("gdal_translate", "-of", "PNG", wgs.as_posix(), png.as_posix())
    if not ok:
        return None

    bounds = await _wgs84_bounds(wgs)
    for tmp in (color_file, rgba, wgs):
        tmp.unlink(missing_ok=True)
    if bounds is None:
        return None
    bounds_file.write_text(json.dumps(bounds), encoding="utf-8")
    return bounds


async def ensure_kmz(work_dir: Path, name: str = "Landslide mask") -> Path | None:
    """Ensure ``result.kmz`` exists for the result in ``work_dir`` and return its
    path (or None). Packages the WGS84 mask PNG as a KML GroundOverlay so it opens
    directly in Google Earth over the correct footprint."""
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
    <color>ffffffff</color>
    <Icon><href>overlay.png</href></Icon>
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


async def _wgs84_bounds(tif: Path) -> list[float] | None:
    """Return [south, west, north, east] from a WGS84 GeoTIFF via gdalinfo -json."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "gdalinfo", "-json", tif.as_posix(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    try:
        corners = json.loads(out)["cornerCoordinates"]
    except (ValueError, KeyError):
        return None
    ul, lr = corners["upperLeft"], corners["lowerRight"]
    west, north = ul[0], ul[1]
    east, south = lr[0], lr[1]
    return [south, west, north, east]
