"""PostgreSQL production test infrastructure.

This module provides test infrastructure for running tests against a real
PostgreSQL database to verify production-grade behavior of the canonical
architecture.
"""

import os
from pathlib import Path

# Test database configuration
# Default to local PostgreSQL; override via TEST_DATABASE_URL env var
TEST_POSTGRES_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test"
)

# Skip PostgreSQL tests if no database available
SKIP_POSTGRES = os.environ.get("SKIP_POSTGRES", "true").lower() == "true"

__all__ = ["TEST_POSTGRES_URL", "SKIP_POSTGRES"]