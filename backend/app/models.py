from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class ProductType(str, Enum):
    SLC = "SENTINEL_1_SLC"
    GRD = "SENTINEL_1_GRD"
    S2_L1C = "SENTINEL_2_L1C"
    S2_L2A = "SENTINEL_2_L2A"
    S3_SLSTR_L2_LST = "SENTINEL_3_SLSTR_L2_LST"
    S3_SLSTR_L2_WST = "SENTINEL_3_SLSTR_L2_WST"
    DEMNAS_25K = "DEMNAS_25K"
    DEMNAS_50K = "DEMNAS_50K"


class SearchQuery(BaseModel):
    productType: list[ProductType] = Field(
        ..., min_length=1, description="Product level(s), multi-select, Sentinel-1 and/or Sentinel-2."
    )
    dateFrom: date = Field(..., description="Start of the sensing time range (inclusive).")
    dateUntil: date = Field(..., description="End of the sensing time range (inclusive).")
    aoi: str = Field(
        ...,
        min_length=1,
        description=(
            "AOI polygon ring as a flat 'lon,lat,lon,lat,...' string. Either the current map "
            "viewport rectangle (default search mode) or a geocoded place's administrative "
            "boundary/bounding box (place AOI mode) - the frontend decides which ring to send."
        ),
    )
    cloudCoverMax: int = Field(
        default=100, ge=0, le=100, description="Max acceptable cloud cover percentage; applies to Sentinel-2 results only."
    )
    skip: int = Field(default=0, ge=0, description="Pagination offset, for Load More.")

    @model_validator(mode="after")
    def check_date_range(self) -> "SearchQuery":
        if self.dateUntil < self.dateFrom:
            raise ValueError("dateUntil must not be before dateFrom")
        return self


class Footprint(BaseModel):
    type: str = Field(default="Polygon")
    coordinates: list[list[list[float]]]


class SearchResultItem(BaseModel):
    id: str
    name: str
    productType: ProductType
    sensingTime: str
    size: str
    polarisation: str
    cloudCoverPercentage: float | None = None
    footprint: Footprint


class ProductAttribute(BaseModel):
    name: str
    value: str


class ProductAttributesResponse(BaseModel):
    attributes: list[ProductAttribute]


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int = Field(..., description="Total matching products at CDSE, which may exceed len(results).")


class GeocodeResponse(BaseModel):
    lat: float
    lng: float
    displayName: str
    bbox: list[float] = Field(..., description="[minLon, minLat, maxLon, maxLat] of the place.")
    polygon: list[list[float]] | None = Field(
        default=None,
        description=(
            "Simplified [lon, lat] ring of the place's administrative boundary, if Nominatim "
            "has one (large/complex polygons are Douglas-Peucker-simplified server-side; "
            "point-only results like POIs have no polygon, only bbox)."
        ),
    )


class GeocodeSuggestionsResponse(BaseModel):
    results: list[GeocodeResponse]


class PreviewResponse(BaseModel):
    productId: str
    tileUrl: str = Field(..., description="WMS/WMTS tile URL for the product imagery.")
    bounds: list[list[float]] = Field(
        ..., description="[[south, west], [north, east]] for Leaflet ImageOverlay bounds."
    )


class ErrorResponse(BaseModel):
    detail: str


class SelectedProductPayload(BaseModel):
    id: str
    name: str
    mission: str
    instrumentName: str
    polarisation: str
    sensingTime: datetime
    size: str
    footprint: Footprint
    attributes: list[ProductAttribute] = Field(default_factory=list)


class SaveSatelliteRequest(BaseModel):
    satelliteName: str = Field(..., min_length=1, max_length=100)
    selectedProduct: SelectedProductPayload

    @field_validator("satelliteName")
    @classmethod
    def _trim_satellite_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("satelliteName must not be blank")
        return trimmed


class SaveSatelliteResponse(BaseModel):
    success: bool
    message: str
    satelliteId: str | None = None


class SavedSatelliteSummary(BaseModel):
    id: str
    satelliteName: str
    mission: str
    instrumentName: str | None
    polarisation: str
    sensingTime: datetime
    size: str
    preview: str | None
    savedAt: datetime
    fileStatus: str | None = None


class SavedSatelliteDetail(SavedSatelliteSummary):
    productId: str
    directoryPath: str
    summary: list[dict[str, str]]
    product: list[dict[str, str]]
    instrument: list[dict[str, str]]
    platform: list[dict[str, str]]
    other: list[dict[str, str]]
    downloadSingleFile: str
    footprint: Footprint
    createdAt: datetime
    updatedAt: datetime


class SavedSatellitesListResponse(BaseModel):
    items: list[SavedSatelliteSummary]
    total: int
    page: int
    pageSize: int


class DeleteSatelliteResponse(BaseModel):
    success: bool
    message: str


class RetryFileDownloadResponse(BaseModel):
    success: bool
    message: str


class ProcessLandslideRequest(BaseModel):
    preSatelliteId: str = Field(..., description="Saved satellite id of the pre-event product.")
    postSatelliteId: str = Field(..., description="Saved satellite id of the post-event product.")
    aoi: list[float] | None = Field(
        default=None,
        description="Optional crop bbox [minLon, minLat, maxLon, maxLat] to speed up processing.",
    )

    @model_validator(mode="after")
    def check_request(self) -> "ProcessLandslideRequest":
        if self.preSatelliteId == self.postSatelliteId:
            raise ValueError("preSatelliteId and postSatelliteId must be different products")
        if self.aoi is not None:
            if len(self.aoi) != 4:
                raise ValueError("aoi must be [minLon, minLat, maxLon, maxLat]")
            min_lon, min_lat, max_lon, max_lat = self.aoi
            if min_lon >= max_lon or min_lat >= max_lat:
                raise ValueError("aoi min must be less than max for both lon and lat")
        return self


class LandslideJobResponse(BaseModel):
    id: str
    name: str
    preSatelliteId: str
    postSatelliteId: str
    status: str
    progress: int
    message: str | None = None
    stage: str | None = None
    stageIndex: int
    totalStages: int
    thresholdDb: float
    hasResult: bool
    createdAt: datetime
    updatedAt: datetime


class LandslideJobsListResponse(BaseModel):
    items: list[LandslideJobResponse]
    total: int


class ActivityLogEntry(BaseModel):
    id: str
    action: str
    category: str
    status: str
    description: str
    progress: int
    createdAt: datetime


class ActivityLogsListResponse(BaseModel):
    items: list[ActivityLogEntry]
    total: int
