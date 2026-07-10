import httpx

from app.auth import TokenManager
from app.config import Settings
from app.models import ProductType
from app.services.cache import get_cached_quicklook_asset_id

# The only Sentinel-3 product type CDSE publishes a QUICKLOOK asset for -
# verified against the live CDSE catalogue this session: 20/20 sampled real
# SL_2_LST products had one, 0/20 sampled real SL_2_WST products did.
_QUICKLOOK_SUPPORTED = {ProductType.S3_SLSTR_L2_LST}


def has_quicklook(product_type: ProductType) -> bool:
    return product_type in _QUICKLOOK_SUPPORTED


def unsupported_preview_message(product_type: ProductType) -> str:
    return (
        f"Citra asli belum tersedia untuk produk {product_type.value} "
        "(Process API Sentinel Hub hanya mendukung koleksi GRD untuk Sentinel-1 "
        "dan L2A untuk Sentinel-2; Sentinel-3 SLSTR L2 WST tidak memiliki "
        "quicklook dari CDSE)."
    )


async def fetch_quicklook_image(
    product_id: str, settings: Settings, token_manager: TokenManager
) -> bytes:
    asset_id = get_cached_quicklook_asset_id(product_id)
    if asset_id is None:
        raise ValueError(
            f"No quicklook preview available for product {product_id} "
            "(CDSE did not publish a QUICKLOOK asset for it)."
        )

    token = await token_manager.get_token()
    headers = {"Authorization": f"Bearer {token}"}
    # CDSE's Assets collection is a sibling of the Products collection under
    # the same OData service root (.../odata/v1/Products -> .../odata/v1/Assets).
    assets_base = settings.cdse_catalogue_url.rsplit("/", 1)[0] + "/Assets"
    url = f"{assets_base}({asset_id})/$value"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        # Same cross-host redirect CDSE uses for full product downloads
        # (see download.py) - httpx does not auto-follow or carry auth across it.
        if response.is_redirect:
            redirect_url = response.headers["location"]
            response = await client.get(redirect_url, headers=headers)
        response.raise_for_status()
        return response.content
