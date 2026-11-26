"""Application-owned PostgreSQL connection pool for C6."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg_pool import AsyncConnectionPool

from waata_api.repositories import PostgresRepository

from .config import Settings


@asynccontextmanager
async def open_repository(settings: Settings) -> AsyncIterator[PostgresRepository]:
    if not settings.database_dsn:
        raise ValueError("WAATA_DATABASE_DSN is required")
    pool = AsyncConnectionPool(
        settings.database_dsn,
        open=False,
        min_size=1,
        max_size=max(4, 2 * settings.worker_concurrency + 2),
        timeout=3,
        kwargs={
            "connect_timeout": 3,
            "options": "-c statement_timeout=5000 -c idle_in_transaction_session_timeout=10000",
        },
        name="waata-platform",
    )
    async with pool:
        await pool.wait(timeout=5)
        async with pool.connection() as conn:
            result = await conn.execute(
                "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = 3)"
            )
            if not (await result.fetchone())[0]:
                raise RuntimeError("Apply the platform SQL migrations before startup")
        yield PostgresRepository(pool)
