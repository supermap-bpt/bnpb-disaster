import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from app.config import get_settings
from app.routers.attributes import router as attributes_router
from app.routers.download import router as download_router
from app.routers.geocode import router as geocode_router
from app.routers.landslide import router as landslide_router
from app.routers.logs import router as logs_router
from app.routers.preview import router as preview_router
from app.routers.satellites import router as satellites_router
from app.routers.search import router as search_router
from fastapi.staticfiles import StaticFiles

settings = get_settings()

# Route application loggers through uvicorn's handler so INFO logs (e.g. the
# landslide SNAP job progress) actually appear on the console. Under uvicorn the
# root logger has no INFO handler, so app.* logs are otherwise dropped.
_app_logger = logging.getLogger("app")
_app_logger.setLevel(logging.INFO)
_uvicorn_handlers = logging.getLogger("uvicorn").handlers
if _uvicorn_handlers:
    _app_logger.handlers = _uvicorn_handlers
    _app_logger.propagate = False
else:  # pragma: no cover - fallback when not run under uvicorn
    logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Sentinel-1 SAR Browser API",
    description=(
        "Backend proxy/orchestrator between the SAR Browser frontend and the "
        "Copernicus Data Space Ecosystem (CDSE). Handles OAuth2 token management, "
        "product search, geocoding, and imagery preview."
    ),
    version="1.0.0",
    openapi_tags=[
        {"name": "System", "description": "Health and operational endpoints."},
        {"name": "Geocoding", "description": "Address-to-coordinate lookups via OpenStreetMap Nominatim."},
        {"name": "Search", "description": "Sentinel-1 SLC/GRD product search against the CDSE Catalogue."},
        {"name": "Preview", "description": "Imagery preview (WMS tile URL) for a selected product."},
        {"name": "Download", "description": "Streamed download of the original product file."},
        {"name": "Attributes", "description": "Raw CDSE catalogue attributes for a selected product."},
        {"name": "Satellites", "description": "Saved (bookmarked) satellite products - CRUD over PostgreSQL."},
        {"name": "Logs", "description": "Activity log entries for Save/Download/Delete operations."},
        {"name": "Landslide", "description": "SNAP SAR change-detection jobs for landslide mapping."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(PydanticValidationError)
async def pydantic_validation_exception_handler(
    request: Request, exc: PydanticValidationError
) -> JSONResponse:
    """Cross-field validators (e.g. SearchQuery's dateUntil >= dateFrom check) raise
    pydantic.ValidationError when the model is built via `Depends()`, which FastAPI does
    not translate into its usual 422 response on its own."""
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": exc.errors()}))


@app.get("/api/health", tags=["System"], summary="Health check")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(geocode_router)
app.include_router(search_router)
app.include_router(preview_router)
app.include_router(download_router)
app.include_router(attributes_router)
app.include_router(satellites_router)
app.include_router(landslide_router)
app.include_router(logs_router)
app.mount("/storage", StaticFiles(directory="storage", check_dir=False), name="storage")
