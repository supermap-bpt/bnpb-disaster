import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values

_backend_dir = Path(__file__).resolve().parents[1]
_env_values = dotenv_values(_backend_dir / ".env")
_real_url = _env_values.get(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/sar_browser"
)
_parts = urlsplit(_real_url)
_db_name = _parts.path.lstrip("/") or "sar_browser"
_test_url = urlunsplit((_parts.scheme, _parts.netloc, f"/{_db_name}_test", _parts.query, _parts.fragment))

os.environ.setdefault("DATABASE_URL", _test_url)

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import Settings, get_settings


@pytest.fixture
def client():
    # Used as a context manager (rather than `return TestClient(app)`) so a
    # single anyio blocking-portal thread/event loop backs every request made
    # through this client. Without `with`, Starlette's TestClient spins up a
    # brand-new portal (new thread + new event loop) per individual request;
    # the first request would bind app.db.session.get_engine()'s `lru_cache`d
    # AsyncEngine/asyncpg pool to that request's ephemeral loop, and the very
    # next request -- on a different ephemeral loop -- would then fail with
    # asyncpg "attached to a different loop" / "event loop is closed" errors.
    # We also clear the engine cache first so this client's portal loop (not
    # pytest-asyncio's session loop, which session-scoped fixtures like
    # `db_engine` run on and may have already cached an engine for) is the one
    # that ends up bound to the cached engine.
    from app.db.session import get_engine

    get_engine.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def override_settings():
    test_settings = Settings(
        cdse_identity_url="https://identity.test/token",
        cdse_catalogue_url="https://catalogue.test/Products",
        cdse_process_url="https://wms.test/process",
        nominatim_url="https://nominatim.test/search",
    )
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield
    app.dependency_overrides.clear()


import pytest_asyncio
from sqlalchemy import text

from app.db.session import Base, get_engine, get_sessionmaker


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(db_engine):
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
