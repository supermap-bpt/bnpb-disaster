"""Renders a flood-mask GeoTIFF into a web-map overlay PNG using the GDAL CLI -
mirrors landslide_preview.py's pipeline exactly (color-relief -> reproject,
capped at 2048px -> PNG, plus KMZ packaging), with a simpler color table:
the flood mask band (`water_and_flood_area`) only ever has value 1 (flood) or
genuine NaN/no-data (everything else, per the Band Maths `else NaN`
expression) - unlike Landslide's 0/1 binary mask, there's no separate "0 vs
no-data" case to handle.

Windows subprocess note: every GDAL invocation runs via the classic blocking
`subprocess` module inside a thread-pool executor (`loop.run_in_executor`),
never `asyncio.create_subprocess_exec` - see app/services/landslide.py's
module docstring for why (SelectorEventLoop, forced by uvicorn on Windows,
cannot spawn subprocesses at all).
"""
import asyncio
import json
import logging
import subprocess
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

# Band index (1-based) of water_and_flood_area in result.tif - the only band.
_FLOOD_MASK_BAND = 1

# Value 1 (flood) -> opaque red; genuine no-data (the `else NaN` branch) ->
# transparent. No separate "0" case - the band never contains a literal 0.
_COLOR_TABLE = "1 255 0 0 255\nnv 0 0 0 0\n"

# Cap the web-preview/KMZ overlay's long edge at this many pixels - same fix
# as Landslide's (a full-scene, high-resolution result.tif produces a PNG too
# large for a browser to decode at native resolution). result.tif itself (the
# actual download) stays full resolution.
_PREVIEW_MAX_DIMENSION = 2048


def _run_blocking(args: tuple[str, ...]) -> bool:
    try:
        result = subprocess.run(args, capture_output=True)
    except FileNotFoundError:
        logger.warning("GDAL tool not found: %s", args[0])
        return False
    if result.returncode != 0:
        out = (result.stdout or b"") + (result.stderr or b"")
        logger.warning("GDAL %s failed: %s", args[0], out.decode(errors="replace")[-500:])
        return False
    return True


async def _run(*args: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_blocking, args)


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
        "gdaldem", "color-relief", "-alpha", "-b", str(_FLOOD_MASK_BAND),
        result.as_posix(), color_file.as_posix(), rgba.as_posix(),
    )
    ok = ok and await _run(
        "gdalwarp", "-t_srs", "EPSG:4326", "-r", "near",
        "-ts", str(_PREVIEW_MAX_DIMENSION), "0",
        "-overwrite", rgba.as_posix(), wgs.as_posix(),
    )
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


async def ensure_kmz(work_dir: Path, name: str = "Flood mask") -> Path | None:
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


def _gdalinfo_json_blocking(tif: Path) -> bytes | None:
    try:
        result = subprocess.run(["gdalinfo", "-json", tif.as_posix()], capture_output=True)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


async def _wgs84_bounds(tif: Path) -> list[float] | None:
    """Return [south, west, north, east] from a WGS84 GeoTIFF via gdalinfo -json."""
    loop = asyncio.get_running_loop()
    out = await loop.run_in_executor(None, _gdalinfo_json_blocking, tif)
    if out is None:
        return None
    try:
        corners = json.loads(out)["cornerCoordinates"]
    except (ValueError, KeyError):
        return None
    ul, lr = corners["upperLeft"], corners["lowerRight"]
    west, north = ul[0], ul[1]
    east, south = lr[0], lr[1]
    return [south, west, north, east]
