from app.models import PreviewResponse
from app.services.cache import get_cached_footprint, get_cached_product_type
from app.services.quicklook import has_quicklook, unsupported_preview_message
from app.services.render import footprint_bbox, is_renderable


async def get_preview(product_id: str) -> PreviewResponse:
    footprint = get_cached_footprint(product_id)
    if footprint is None:
        raise ValueError(f"No cached footprint for product {product_id}. Run a search first.")

    product_type = get_cached_product_type(product_id)
    if product_type is not None and not (is_renderable(product_type) or has_quicklook(product_type)):
        raise ValueError(unsupported_preview_message(product_type))

    min_lon, min_lat, max_lon, max_lat = footprint_bbox(footprint)
    bounds = [[min_lat, min_lon], [max_lat, max_lon]]

    # Relative path: the browser fetches this from our own backend, which
    # renders the real acquisition image server-side via the Process API
    # (render.py) - the browser never talks to Sentinel Hub or holds a token.
    tile_url = f"/api/preview-image/{product_id}"

    return PreviewResponse(productId=product_id, tileUrl=tile_url, bounds=bounds)
