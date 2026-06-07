"""
Database connection pool management for avry-careers service.

Uses asyncpg with:
- Connection pooling
- Health check endpoint support
- Exponential backoff retry on connection loss (1s, 2s, 4s, 8s, 16s — max 5 retries)
"""

import asyncio
import logging
from typing import Any, Optional

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None

# Retry configuration
MAX_RETRIES = 5
BASE_DELAY_SECONDS = 1  # Exponential backoff: 1, 2, 4, 8, 16


async def create_pool() -> asyncpg.Pool:
    """Create the asyncpg connection pool with retry logic."""
    global _pool

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            logger.info("✓ Database connection pool created successfully")
            return _pool
        except (asyncpg.PostgresError, OSError, ConnectionRefusedError) as e:
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                f"Database connection attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                f"Retrying in {delay}s..."
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Failed to connect to database after {MAX_RETRIES} attempts"
                )
                raise

    # Should not reach here, but satisfy type checker
    raise RuntimeError("Failed to create database pool")


async def get_pool() -> asyncpg.Pool:
    """Get the current connection pool, creating it if necessary."""
    global _pool
    if _pool is None or _pool._closed:
        await create_pool()
    return _pool


async def close_pool() -> None:
    """Close the connection pool gracefully."""
    global _pool
    if _pool is not None and not _pool._closed:
        await _pool.close()
        logger.info("Database connection pool closed")
    _pool = None


async def health_check() -> bool:
    """
    Check if the database is reachable.

    Returns True if a simple query succeeds, False otherwise.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def execute_query(query: str, *args: Any) -> str:
    """
    Execute a query that does not return rows (INSERT, UPDATE, DELETE).

    Retries with exponential backoff on connection failure.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                return await conn.execute(query, *args)
        except (asyncpg.InterfaceError, OSError, ConnectionRefusedError) as e:
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                f"Query execution attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                f"Retrying in {delay}s..."
            )
            if attempt < MAX_RETRIES:
                # Reset pool on connection issues
                await close_pool()
                await asyncio.sleep(delay)
            else:
                logger.error(f"Query failed after {MAX_RETRIES} retries")
                raise

    raise RuntimeError("Query execution failed")


async def fetch_one(query: str, *args: Any) -> Optional[asyncpg.Record]:
    """
    Fetch a single row from the database.

    Retries with exponential backoff on connection failure.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except (asyncpg.InterfaceError, OSError, ConnectionRefusedError) as e:
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                f"Fetch one attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                f"Retrying in {delay}s..."
            )
            if attempt < MAX_RETRIES:
                await close_pool()
                await asyncio.sleep(delay)
            else:
                logger.error(f"Fetch one failed after {MAX_RETRIES} retries")
                raise

    raise RuntimeError("Fetch one failed")


async def fetch_all(query: str, *args: Any) -> list[asyncpg.Record]:
    """
    Fetch multiple rows from the database.

    Retries with exponential backoff on connection failure.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except (asyncpg.InterfaceError, OSError, ConnectionRefusedError) as e:
            delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                f"Fetch all attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                f"Retrying in {delay}s..."
            )
            if attempt < MAX_RETRIES:
                await close_pool()
                await asyncio.sleep(delay)
            else:
                logger.error(f"Fetch all failed after {MAX_RETRIES} retries")
                raise

    raise RuntimeError("Fetch all failed")
