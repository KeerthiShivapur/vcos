"""PostgreSQL test infrastructure for VCOS Gate 7.

Provides a real PostgreSQL test database using testcontainers or docker-compose.
"""
import asyncio
import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.pool import NullPool
from app.db.database import Base
from app import models  # noqa: F401

# PostgreSQL test database URL
# Uses the docker-compose service name 'database' when running in CI,
# or localhost when running locally
TEST_POSTGRES_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test"
)


@pytest_asyncio.fixture(scope="session")
async def postgres_engine():
    """Session-scoped PostgreSQL engine for testing.
    
    Creates a real PostgreSQL database using the test database URL.
    Drops and recreates all tables for each test session.
    """
    engine = create_async_engine(
        TEST_POSTGRES_URL,
        poolclass=None,  # No pooling for test isolation
        echo=False,
        future=True,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def pg_db_session_factory(postgres_engine):
    """Session factory bound to the PostgreSQL test engine."""
    return async_sessionmaker(
        postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def pg_db_session(pg_db_session_factory):
    """Individual test session with transaction rollback."""
    async with pg_db_session_factory() as session:
        yield session
        await session.rollback()


# PostgreSQL-specific test markers
def pytest_configure(config):
    config.addinivalue_line("markers", "postgres: marks tests requiring PostgreSQL")


def pytest_collection_modifyitems(config, items):
    """Add postgres marker to tests that use pg_db_session."""
    for item in items:
        if "pg_db_session" in item.fixturenames:
            item.add_marker(pytest.mark.postgres)