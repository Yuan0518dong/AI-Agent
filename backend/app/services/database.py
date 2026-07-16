import os
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Engine, create_engine, text


class DatabaseConfigurationError(RuntimeError):
    pass


_engine: Engine | None = None
_engine_url: str | None = None
_force_sqlite_for_tests = False


def set_sqlite_test_mode(enabled: bool) -> None:
    global _force_sqlite_for_tests
    _force_sqlite_for_tests = enabled


def using_postgres() -> bool:
    if _force_sqlite_for_tests:
        return False
    return _configured_url().startswith("postgresql+")


def require_runtime_database_configuration() -> None:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    url = os.getenv("DATABASE_URL", "").strip()
    if app_env == "production" and not url:
        raise DatabaseConfigurationError("DATABASE_URL is required when APP_ENV=production.")
    if not url:
        return
    normalized_url = _normalize_url(url)
    if normalized_url.startswith("postgresql+psycopg://"):
        if app_env == "production":
            _require_neon_connection(normalized_url, require_pooler=True, setting_name="DATABASE_URL")
        return
    if app_env != "production" and normalized_url.startswith("sqlite"):
        return
    raise DatabaseConfigurationError(
        "DATABASE_URL must use PostgreSQL with psycopg (SQLite is only allowed outside production for local tests)."
    )


def validate_migration_database_url(url: str) -> str:
    normalized_url = _normalize_url(url)
    if not normalized_url.startswith("postgresql+psycopg://"):
        raise DatabaseConfigurationError(
            "MIGRATION_DATABASE_URL must use PostgreSQL with the psycopg driver."
        )
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        _require_neon_connection(
            normalized_url,
            require_pooler=False,
            setting_name="MIGRATION_DATABASE_URL",
        )
    return normalized_url


def get_engine() -> Engine:
    global _engine, _engine_url
    url = _configured_url()
    if not url.startswith("postgresql+psycopg://"):
        raise DatabaseConfigurationError("A PostgreSQL DATABASE_URL is required for the SQLAlchemy repository.")
    if _engine is None or _engine_url != url:
        if _engine is not None:
            _engine.dispose()
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "5")),
        )
        _engine_url = url
    return _engine


def ensure_postgres_schema_ready() -> None:
    with get_engine().connect() as connection:
        table_name = connection.execute(text("SELECT to_regclass('public.users')")).scalar_one()
    if table_name != "users":
        raise DatabaseConfigurationError(
            "PostgreSQL schema is not migrated. Run Alembic with MIGRATION_DATABASE_URL before starting the app."
        )


def connect() -> "SqlAlchemyCompatConnection":
    return SqlAlchemyCompatConnection(get_engine())


class SqlAlchemyCompatResult:
    def __init__(self, result: Any):
        self._result = result
        self.rowcount = result.rowcount

    def fetchone(self) -> dict[str, Any] | None:
        row = self._result.mappings().first()
        return dict(row) if row is not None else None

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._result.mappings().all()]


class SqlAlchemyCompatConnection:
    """Small qmark/row facade used while existing services keep their repository interfaces."""

    def __init__(self, engine: Engine):
        self._connection = engine.connect()
        self._transaction = None
        self._closed = False

    def __enter__(self) -> "SqlAlchemyCompatConnection":
        self._transaction = self._connection.begin()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._transaction is not None and self._transaction.is_active:
            if exc_type is None:
                self._transaction.commit()
            else:
                self._transaction.rollback()
        self.close()

    def execute(self, statement: str, parameters: Any = None) -> SqlAlchemyCompatResult:
        sql, binds = _prepare_statement(statement, parameters)
        return SqlAlchemyCompatResult(self._connection.execute(text(sql), binds))

    def executemany(self, statement: str, parameters: Any) -> SqlAlchemyCompatResult:
        """Execute SQLite-style batch writes through one SQLAlchemy statement."""
        rows = list(parameters)
        if not rows:
            return SqlAlchemyCompatResult(self._connection.execute(text("SELECT 1 WHERE 1 = 0")))

        sql, first_binds = _prepare_statement(statement, rows[0])
        bindings = [first_binds]
        for row in rows[1:]:
            row_sql, row_binds = _prepare_statement(statement, row)
            if row_sql != sql:
                raise DatabaseConfigurationError("Batch SQL placeholders must be consistent.")
            bindings.append(row_binds)
        return SqlAlchemyCompatResult(self._connection.execute(text(sql), bindings))

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True


def _configured_url() -> str:
    require_runtime_database_configuration()
    raw_url = os.getenv("DATABASE_URL", "").strip()
    return _normalize_url(raw_url) if raw_url else ""


def _normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _require_neon_connection(url: str, *, require_pooler: bool, setting_name: str) -> None:
    hostname = urlsplit(url).hostname or ""
    hostname = hostname.lower()
    if not hostname.endswith(".neon.tech"):
        raise DatabaseConfigurationError(
            f"{setting_name} must point to Neon PostgreSQL in production."
        )
    is_pooler = "-pooler." in hostname
    if require_pooler and not is_pooler:
        raise DatabaseConfigurationError(
            f"{setting_name} must use Neon's pooled host in production."
        )
    if not require_pooler and is_pooler:
        raise DatabaseConfigurationError(
            f"{setting_name} must use Neon's direct host for Alembic migrations."
        )


def _prepare_statement(statement: str, parameters: Any) -> tuple[str, dict[str, Any]]:
    if parameters is None:
        return statement, {}
    if isinstance(parameters, dict):
        return statement, parameters

    values = list(parameters)
    bound_names: dict[str, Any] = {}
    sql = statement
    for index, value in enumerate(values):
        name = f"p{index}"
        if "?" not in sql:
            raise DatabaseConfigurationError("SQL parameter count does not match qmark placeholders.")
        sql = sql.replace("?", f":{name}", 1)
        bound_names[name] = value
    if "?" in sql:
        raise DatabaseConfigurationError("SQL qmark placeholder does not have a bound value.")
    return sql, bound_names
