import asyncio
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from app.db.database import Base
from app import models

def create_tables():
    engine = create_engine(
        'postgresql+psycopg2://postgres:postgres@localhost:5432/vcos_gate7',
        poolclass=NullPool,
        echo=False
    )
    Base.metadata.create_all(engine)
    engine.dispose()
    print('Tables created')

create_tables()