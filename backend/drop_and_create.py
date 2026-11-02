from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.db.database import Base
from app import models

engine = create_engine(
    'postgresql+psycopg2://postgres:postgres@localhost:5432/vcos_gate7',
    poolclass=NullPool,
    echo=False,
    isolation_level="AUTOCOMMIT"
)

# Drop everything using raw SQL
with engine.connect() as conn:
    conn.execute(text("DROP SCHEMA public CASCADE"))
    conn.execute(text("CREATE SCHEMA public"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
    conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    print('Schema dropped and recreated')

engine.dispose()

# Now create tables with a new engine
engine2 = create_engine(
    'postgresql+psycopg2://postgres:postgres@localhost:5432/vcos_gate7',
    poolclass=NullPool,
    echo=False
)
Base.metadata.create_all(engine2)
engine2.dispose()
print('Tables created')