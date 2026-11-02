"""Run migrations on test database."""
import asyncio
import os
import sys

# Set test database URL
os.environ["TEST_DATABASE_URL"] = "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test"

# Now import and run migrations
from alembic.config import Config
from alembic import command

def run_migrations():
    alembic_cfg = Config("alembic.ini")
    # Override the database URL
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://vcos:vcos@localhost:5432/vcos_test"
    
    # Run upgrade
    command.upgrade(Config("alembic.ini"), "head")

if __name__ == "__main__":
    run_migrations()