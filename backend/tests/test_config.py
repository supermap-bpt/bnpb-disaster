import os

from app.config import Settings


def test_database_url_defaults_to_local_postgres():
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_database_url_reads_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pw@otherhost:5432/otherdb")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://user:pw@otherhost:5432/otherdb"
