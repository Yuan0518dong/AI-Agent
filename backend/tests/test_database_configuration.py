import pytest

from backend.app.services import database


def test_production_database_configuration_does_not_fall_back_to_sqlite(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database.set_sqlite_test_mode(False)
    with pytest.raises(database.DatabaseConfigurationError, match="DATABASE_URL is required"):
        database.require_runtime_database_configuration()
    database.set_sqlite_test_mode(True)


def test_production_requires_neon_pooled_runtime_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db.example.test/app")
    database.set_sqlite_test_mode(False)
    with pytest.raises(database.DatabaseConfigurationError, match="Neon PostgreSQL"):
        database.require_runtime_database_configuration()
    database.set_sqlite_test_mode(True)


def test_production_requires_neon_direct_migration_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(database.DatabaseConfigurationError, match="direct host"):
        database.validate_migration_database_url(
            "postgresql+psycopg://user:password@ep-demo-pooler.us-east-2.aws.neon.tech/app"
        )
