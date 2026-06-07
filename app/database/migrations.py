"""
Database migration runner for avry-careers service.

Reads SQL migration files from the migrations/ directory and executes them
in order on startup. Tracks applied migrations to avoid re-running.
"""

import logging
import os
from pathlib import Path

import asyncpg

from app.database.connection import get_pool

logger = logging.getLogger(__name__)

# Migrations directory relative to the service root
MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    """Create the migration tracking table if it doesn't exist."""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) UNIQUE NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def get_applied_migrations(conn: asyncpg.Connection) -> set[str]:
    """Get the set of already-applied migration filenames."""
    rows = await conn.fetch("SELECT filename FROM _migrations ORDER BY id")
    return {row["filename"] for row in rows}


async def run_migrations() -> None:
    """
    Run all pending SQL migrations from the migrations/ directory.

    Migrations are executed in alphabetical order (e.g., 001_xxx.sql, 002_xxx.sql).
    Each migration is run inside a transaction. Already-applied migrations are skipped.
    """
    if not MIGRATIONS_DIR.exists():
        logger.warning(f"Migrations directory not found: {MIGRATIONS_DIR}")
        return

    # Collect SQL migration files sorted by name
    migration_files = sorted(
        f for f in MIGRATIONS_DIR.iterdir()
        if f.suffix == ".sql" and f.is_file()
    )

    if not migration_files:
        logger.info("No migration files found")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_migrations_table(conn)
        applied = await get_applied_migrations(conn)

        for migration_file in migration_files:
            filename = migration_file.name

            if filename in applied:
                logger.debug(f"Migration already applied: {filename}")
                continue

            logger.info(f"Applying migration: {filename}")
            sql = migration_file.read_text(encoding="utf-8")

            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO _migrations (filename) VALUES ($1)",
                        filename,
                    )
                logger.info(f"✓ Migration applied: {filename}")
            except Exception as e:
                logger.error(f"✗ Migration failed: {filename} — {e}")
                raise

    logger.info("All migrations applied successfully")
