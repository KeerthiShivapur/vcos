import asyncio
import uuid
from sqlalchemy import create_engine, Column, String, Integer, select, update
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

Base = declarative_base()

class TestEntity(Base):
    __tablename__ = 'test_entity'
    id = Column(String(32), primary_key=True)
    title = Column(String(100))
    version = Column(Integer, default=1)

async def test():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(TestEntity.__table__.create)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Create initial entity
    async with async_session() as session:
        entity = TestEntity(id='test-1', title='Original', version=1)
        session.add(entity)
        await session.flush()
        await session.commit()
    
    # Simulate 3 concurrent updates WITHOUT barrier
    async def worker(worker_id):
        async with async_session() as session:
            from sqlalchemy import update
            stmt = (
                update(TestEntity)
                .where(TestEntity.id == 'test-1')
                .where(TestEntity.version == 1)
                .values(title=f'Updated by {worker_id}', version=2)
                .returning(TestEntity)
            )
            result = await session.execute(stmt)
            await session.flush()
            updated = result.scalar_one_or_none()
            print(f'Worker {worker_id}: updated={updated is not None}')
            if updated:
                await session.commit()
            else:
                await session.rollback()
    
    # Run 3 concurrent workers
    await asyncio.gather(*[worker(i) for i in range(3)])

if __name__ == '__main__':
    asyncio.run(test())