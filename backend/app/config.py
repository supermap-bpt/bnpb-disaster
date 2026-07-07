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
    # Plain str, not list[str]: pydantic-settings tries json.loads() on any
    # list-typed env var before validators run, and .env stores this as a
    # plain comma-separated string (CORS_ORIGINS=http://localhost:5173,...).
    cors_origins_raw: str = Field(default="http://localhost:5173", validation_alias="CORS_ORIGINS")
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sar_browser"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
