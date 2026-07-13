from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    cdse_client_id: str = ""
    cdse_client_secret: str = ""
    # CDSE's download/zipper service rejects client_credentials tokens from a
    # Sentinel Hub OAuth client ("Token audience not allowed") - downloading
    # the actual product file requires a user-account password-grant token
    # against the public "cdse-public" client instead.
    cdse_username: str = ""
    cdse_password: str = ""
    cdse_identity_url: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    cdse_catalogue_url: str = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
    # Sentinel Hub Process API (POST, JSON body) - confirmed working against
    # real CDSE this session. Previously misnamed "cdse_wms_url" and misused
    # with GET query-string WMS params, which is a different protocol this
    # endpoint does not accept (root cause of the old broken Preview).
    cdse_process_url: str = "https://sh.dataspace.copernicus.eu/api/v1/process"
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    demnas_url: str = "https://tanahair.indonesia.go.id/portal-web/demnas.json"
    # Plain str, not list[str]: pydantic-settings tries json.loads() on any
    # list-typed env var before validators run, and .env stores this as a
    # plain comma-separated string (CORS_ORIGINS=http://localhost:5173,...).
    cors_origins_raw: str = Field(default="http://localhost:5173", validation_alias="CORS_ORIGINS")
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sar_browser"
    # ESA SNAP Graph Processing Tool. Default assumes `gpt` is on PATH; override
    # via SNAP_GPT_PATH env var to an absolute path (e.g. /opt/snap/bin/gpt).
    snap_gpt_path: str = Field(default="gpt", validation_alias="SNAP_GPT_PATH")
    # Backscatter-drop cutoff (dB) for the landslide binary mask, per the reference paper.
    landslide_threshold_db: float = -2.0
    # Pixels whose pre- OR post-event Sigma0_VV is below this (dB) are treated as
    # water / radar shadow / smooth surfaces and excluded from the landslide mask.
    # Land/vegetation VV is typically > -15 dB; open water is < -20 dB.
    landslide_water_threshold_db: float = -17.0
    # Sigma0 (linear, not dB) cutoff for the flood binary mask, per the reference PDF.
    flood_threshold_sigma0: float = 0.0137

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
