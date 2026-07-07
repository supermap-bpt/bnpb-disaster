from fastapi import APIRouter, HTTPException

from app.models import ProductAttribute, ProductAttributesResponse
from app.services.cache import get_cached_attributes

router = APIRouter()


@router.get(
    "/api/products/{productId}/attributes",
    response_model=ProductAttributesResponse,
    tags=["Attributes"],
    summary="Get the raw CDSE catalogue attributes for a selected product",
    description=(
        "Returns every {Name, Value} attribute CDSE attached to the product (orbit "
        "numbers, processing metadata, platform/instrument fields, etc.), exactly as "
        "received via $expand=Attributes on /api/search. The product must have been "
        "cached by a prior search."
    ),
)
async def get_attributes(productId: str) -> ProductAttributesResponse:
    attributes = get_cached_attributes(productId)
    if attributes is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached data for product {productId}. Run a search first.",
        )
    return ProductAttributesResponse(
        attributes=[
            ProductAttribute(name=attr.get("Name", ""), value=str(attr.get("Value", "")))
            for attr in attributes
        ]
    )
