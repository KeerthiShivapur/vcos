#!/usr/bin/env python
"""Create all tables using raw SQL with proper FK ordering"""
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql.ddl import sort_tables_and_constraints
from app.db.database import Base
from app import models  # noqa: F401

# Use the sync engine
engine = create_engine(
    'postgresql+psycopg2://postgres:postgres@localhost:5432/vcos_gate7',
    poolclass=NullPool,
    echo=False
)

# Sort tables by foreign key dependencies
tables = list(Base.metadata.tables.values())
sorted_tables = sort_tables_and_constraints(tables)

# Create all tables in separate transactions to avoid FK issues
with engine.connect() as conn:
    # Enable autocommit
    conn.execution_options(isolation_level="AUTOCOMMIT")
    
    for table, fks in sorted_tables:
        if table is not None:
            create_sql = str(CreateTable(table).compile(engine))
            print(f"Creating: {table.name}")
            try:
                conn.execute(text(create_sql))
            except Exception as e:
                print(f"  Error creating {table.name}: {e}")
                # Continue with other tables

print('All table creation attempted')

engine.dispose()