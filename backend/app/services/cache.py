from app.models import Footprint, ProductType

_FOOTPRINT_CACHE: dict[str, Footprint] = {}
_PRODUCT_NAME_CACHE: dict[str, str] = {}
_SIZE_CACHE: dict[str, str] = {}
_SENSING_TIME_CACHE: dict[str, str] = {}
_PRODUCT_TYPE_CACHE: dict[str, ProductType] = {}
_ATTRIBUTES_CACHE: dict[str, list[dict]] = {}


def cache_footprint(product_id: str, footprint: Footprint) -> None:
    _FOOTPRINT_CACHE[product_id] = footprint


def get_cached_footprint(product_id: str) -> Footprint | None:
    return _FOOTPRINT_CACHE.get(product_id)


def cache_product_name(product_id: str, name: str) -> None:
    _PRODUCT_NAME_CACHE[product_id] = name


def get_cached_product_name(product_id: str) -> str | None:
    return _PRODUCT_NAME_CACHE.get(product_id)


def cache_product_size(product_id: str, size: str) -> None:
    _SIZE_CACHE[product_id] = size


def get_cached_product_size(product_id: str) -> str | None:
    return _SIZE_CACHE.get(product_id)


def cache_sensing_time(product_id: str, sensing_time: str) -> None:
    _SENSING_TIME_CACHE[product_id] = sensing_time


def get_cached_sensing_time(product_id: str) -> str | None:
    return _SENSING_TIME_CACHE.get(product_id)


def cache_product_type(product_id: str, product_type: ProductType) -> None:
    _PRODUCT_TYPE_CACHE[product_id] = product_type


def get_cached_product_type(product_id: str) -> ProductType | None:
    return _PRODUCT_TYPE_CACHE.get(product_id)


def cache_attributes(product_id: str, attributes: list[dict]) -> None:
    _ATTRIBUTES_CACHE[product_id] = attributes


def get_cached_attributes(product_id: str) -> list[dict] | None:
    return _ATTRIBUTES_CACHE.get(product_id)


_QUICKLOOK_ASSET_ID_CACHE: dict[str, str] = {}


def cache_quicklook_asset_id(product_id: str, asset_id: str) -> None:
    _QUICKLOOK_ASSET_ID_CACHE[product_id] = asset_id


def get_cached_quicklook_asset_id(product_id: str) -> str | None:
    return _QUICKLOOK_ASSET_ID_CACHE.get(product_id)
