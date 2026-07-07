import math

import httpx

from app.auth import TokenManager
from app.config import Settings
from app.models import Footprint, ProductType
from app.services.cache import get_cached_footprint, get_cached_sensing_time

# Sentinel Hub Process API data-collection identifiers, by product type.
# Sentinel-1 SLC and Sentinel-2 L1C are NOT recognized collections here
# (confirmed against real CDSE for SLC: POST with type="sentinel-1-slc" ->
# 400 "Invalid collection type" - SLC is complex-valued raw radar data, not
# directly renderable this way; L1C is left unmapped by product decision,
# matching the SLC precedent, since L2A is already atmospheric-corrected
# and ready for true-color display).
_PROCESS_COLLECTION: dict[ProductType, str] = {
    ProductType.GRD: "sentinel-1-grd",
    ProductType.S2_L2A: "sentinel-2-l2a",
}

# Source: https://github.com/sentinel-hub/custom-scripts (CC BY 4.0),
# sentinel-1/sar_false_color_visualization/script.js, by Annamaria Luongo -
# wrapped in the required evalscript V3 setup()/evaluatePixel() structure.
# Verified against real CDSE this session (renders a correct false-color
# SAR image, coastline clearly visible).
EVALSCRIPT_S1_SAR = """//VERSION=3
function setup() {
  return {
    input: ["VV", "VH"],
    output: { bands: 3 },
  };
}

function evaluatePixel(sample) {
  var VV = sample.VV;
  var VH = sample.VH;
  var c1 = 10e-4;
  var c2 = 0.01;
  var c3 = 0.02;
  var c4 = 0.03;
  var c5 = 0.045;
  var c6 = 0.05;
  var c7 = 0.9;
  var c8 = 0.25;

  var band1 = c4 + Math.log(c1 - Math.log(c6 / (c3 + 2 * VV)));
  var band2 = c6 + Math.exp(c8 * (Math.log(c2 + 2 * VV) + Math.log(c3 + 5 * VH)));
  var band3 = 1 - Math.log(c6 / (c5 - c7 * VV));

  return [band1, band2, band3];
}
"""

# Source: https://github.com/sentinel-hub/custom-scripts (CC BY 4.0),
# sentinel-2/true_color/script.js - standard Sentinel-2 true-color RGB
# (bands B04/B03/B02) with a fixed gain factor.
EVALSCRIPT_S2_TRUE_COLOR = """//VERSION=3
function setup() {
  return {
    input: ["B02", "B03", "B04"],
    output: { bands: 3 },
  };
}

function evaluatePixel(sample) {
  return [2.5 * sample.B04, 2.5 * sample.B03, 2.5 * sample.B02];
}
"""

_EVALSCRIPTS: dict[ProductType, str] = {
    ProductType.GRD: EVALSCRIPT_S1_SAR,
    ProductType.S2_L2A: EVALSCRIPT_S2_TRUE_COLOR,
}

_MAX_METERS_PER_PIXEL = 1400.0  # CDSE's S1GRD limit is 1500 m/px; small margin.
_MIN_OUTPUT_DIM = 200
_MAX_OUTPUT_DIM = 512


def is_renderable(product_type: ProductType) -> bool:
    return product_type in _PROCESS_COLLECTION


def footprint_bbox(footprint: Footprint) -> list[float]:
    points = [point for ring in footprint.coordinates for point in ring]
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return [min(lons), min(lats), max(lons), max(lats)]


def _output_size(bbox: list[float]) -> tuple[int, int]:
    min_lon, min_lat, max_lon, max_lat = bbox
    mid_lat_rad = math.radians((min_lat + max_lat) / 2)
    width_m = (max_lon - min_lon) * 111_320 * math.cos(mid_lat_rad)
    height_m = (max_lat - min_lat) * 111_320
    width_px = max(_MIN_OUTPUT_DIM, min(_MAX_OUTPUT_DIM, math.ceil(width_m / _MAX_METERS_PER_PIXEL)))
    height_px = max(_MIN_OUTPUT_DIM, min(_MAX_OUTPUT_DIM, math.ceil(height_m / _MAX_METERS_PER_PIXEL)))
    return width_px, height_px


def _day_time_range(sensing_time: str) -> tuple[str, str]:
    date_part = sensing_time[:10]
    return f"{date_part}T00:00:00Z", f"{date_part}T23:59:59Z"


async def render_product_image(
    product_id: str,
    product_type: ProductType,
    settings: Settings,
    token_manager: TokenManager,
) -> bytes:
    collection = _PROCESS_COLLECTION.get(product_type)
    if collection is None:
        raise ValueError(
            f"Citra asli belum tersedia untuk produk {product_type.value} "
            "(Process API Sentinel Hub hanya mendukung koleksi GRD untuk Sentinel-1 "
            "dan L2A untuk Sentinel-2)."
        )

    footprint = get_cached_footprint(product_id)
    sensing_time = get_cached_sensing_time(product_id)
    if footprint is None or sensing_time is None:
        raise ValueError(f"No cached data for product {product_id}. Run a search first.")

    bbox = footprint_bbox(footprint)
    width, height = _output_size(bbox)
    time_from, time_to = _day_time_range(sensing_time)
    token = await token_manager.get_token()

    body = {
        "input": {
            "bounds": {"bbox": bbox},
            "data": [
                {
                    "type": collection,
                    "dataFilter": {"timeRange": {"from": time_from, "to": time_to}},
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": _EVALSCRIPTS[product_type],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            settings.cdse_process_url,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.content
