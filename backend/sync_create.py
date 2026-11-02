#!/usr/bin/env python
"""Create tables using synchronous psycopg2"""
from sqlalchemy import create_engine, MetaData
from sqlalchemy.pool import NullPool
from app.db.database import Base
from app import models  # noqa: F401

engine = create_engine(
    'postgresql+psycopg2://postgres:postgres@localhost:5432/vcos_gate7',
    poolclass=NullPool,
    echo=False
)

# Drop all tables first (in case)
Base.metadata.drop_all(engine, checkfirst=False)
print('Dropped all tables')

# Create all tables
Base.metadata.create_all(engine, checkfirst=False)
print('Created all tables')

engine.dispose()