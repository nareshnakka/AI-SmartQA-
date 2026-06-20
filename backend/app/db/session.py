from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.base import Base

_connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    _connect_args["timeout"] = 30

engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,
    future=True,
    connect_args=_connect_args,
)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    import app.db.models  # noqa: F401 — register models with Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite)
    async with AsyncSessionLocal() as session:
        from app.services.auth import seed_default_admin
        from app.services.modules import backfill_module_environments
        from app.services.runner_agent import ensure_localhost_agent
        await seed_default_admin(session)
        await ensure_localhost_agent(session)
        await backfill_module_environments(session)
        await session.commit()


def _migrate_sqlite(conn) -> None:
    """Add missing columns on existing SQLite DBs (create_all does not alter)."""
    if conn.dialect.name != "sqlite":
        return
    migrations = [
        ("users", "auth_provider", "VARCHAR(30) DEFAULT 'local'"),
        ("users", "external_id", "VARCHAR(255)"),
        ("performance_assets", "throughput_config", "JSON"),
        ("performance_assets", "scenarios", "JSON DEFAULT '[]'"),
        ("performance_assets", "parameterization", "JSON"),
        ("performance_assets", "data_pools", "JSON DEFAULT '[]'"),
        ("performance_assets", "parent_id", "CHAR(36)"),
        ("performance_assets", "updated_at", "DATETIME"),
        ("discovery_sessions", "proposed_test_cases", "JSON DEFAULT '[]'"),
        ("discovery_sessions", "navigation_log", "JSON DEFAULT '[]'"),
        ("execution_runs", "test_case_ids", "JSON DEFAULT '[]'"),
        ("execution_runs", "run_name", "VARCHAR(255)"),
        ("execution_runs", "sprint", "VARCHAR(100)"),
        ("execution_runs", "release", "VARCHAR(100)"),
        ("execution_runs", "agent_id", "VARCHAR(36)"),
        ("execution_runs", "progress", "JSON"),
        ("test_cases", "module_id", "CHAR(36)"),
        ("test_cases", "environment_id", "CHAR(36)"),
        ("project_modules", "environment_id", "CHAR(36)"),
        ("projects", "naming_patterns", "JSON"),
        ("test_cases", "case_code", "VARCHAR(120)"),
    ]
    for table, column, col_type in migrations:
        try:
            conn.execute(__import__("sqlalchemy").text(f"SELECT {column} FROM {table} LIMIT 1"))
        except Exception:
            try:
                conn.execute(__import__("sqlalchemy").text(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                ))
            except Exception:
                pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
