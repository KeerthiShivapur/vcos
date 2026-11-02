from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql.ddl import sort_tables_and_constraints
from app.db.database import Base
from app import models

# Use the sync engine to generate and execute SQL
engine = create_engine(
    'postgresql+psycopg2://postgres:postgres@localhost:5432/vcos_gate7',
    poolclass=NullPool,
    echo=False,
    isolation_level="AUTOCOMMIT"
)

# First drop everything
with engine.connect() as conn:
    conn.execute(text("DROP SCHEMA public CASCADE"))
    conn.execute(text("CREATE SCHEMA public"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    print('Schema recreated')

engine.dispose()

# Now generate and execute CREATE TABLE statements
engine2 = create_engine(
    'postgresql+psycopg2://postgres:postgres@localhost:5432/vcos_gate7',
    poolclass=NullPool,
    echo=False
)

# Sort tables by foreign key dependencies
tables = list(Base.metadata.tables.values())
sorted_tables = sort_tables_and_constraints(tables)

with engine2.connect() as conn:
    for table, fks in sorted_tables:
        if table is not None:
            create_sql = str(CreateTable(table).compile(engine2))
            print(f"Creating: {table.name}")
            try:
                conn.execute(text(create_sql))
            except Exception as e:
                print(f"Error creating {table.name}: {e}")
    conn.commit()

engine2.dispose()
print('All tables created via raw SQL')