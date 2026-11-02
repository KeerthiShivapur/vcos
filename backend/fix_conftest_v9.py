with open('tests/conftest.py', 'r') as f:
    content = f.read()

# Fix the pg_db_session fixture to use the same session factory for cleanup
old = '''@pytest_asyncio.fixture(scope="function")
async def pg_db_session(pg_db_session_factory):
    """Individual test session - test manages its own lifecycle."""
    session = pg_db_session_factory()
    session.expire_on_commit = False
    
    # Initialize adapter registry for tests
    from app.services.adapter_registry import adapter_registry
    from app.core.config import get_settings
    if not adapter_registry._initialized:
        adapter_registry.initialize(get_settings())
    
    # Clean up Connector records before each test to ensure fresh state
    from app.models.canonical_integration import Connector
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import get_settings
    settings = get_settings()
    cleanup_engine = create_async_engine(settings.DATABASE_URL, poolclass=None)
    cleanup_session_factory = async_sessionmaker(cleanup_engine, class_=AsyncSession, expire_on_commit=False)
    async with cleanup_session_factory() as cleanup_session:
        from sqlalchemy import delete
        from app.models.canonical_integration import Connector
        await cleanup_session.execute(delete(Connector))
        await cleanup_session.commit()
    
    yield pg_db_session_factory()
    # Test is responsible for closing the session'''

new = '''@pytest_asyncio.fixture(scope="function")
async def pg_db_session(pg_db_session_factory):
    """Individual test session - test manages its own lifecycle."""
    session = pg_db_session_factory()
    session.expire_on_commit = False
    
    # Initialize adapter registry for tests
    from app.services.adapter_registry import adapter_registry
    from app.core.config import get_settings
    if not adapter_registry._initialized:
        adapter_registry.initialize(get_settings())
    
    # Clean up Connector records before each test to ensure fresh state
    from app.models.canonical_integration import Connector
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.config import get_settings
    settings = get_settings()
    cleanup_engine = create_async_engine(settings.DATABASE_URL, poolclass=None)
    cleanup_session_factory = async_sessionmaker(cleanup_engine, class_=AsyncSession, expire_on_commit=False)
    async with cleanup_session_factory() as cleanup_session:
        from sqlalchemy import delete
        from app.models.canonical_integration import Connector
        await cleanup_session.execute(delete(Connector))
        await cleanup_session.commit()
    
    yield pg_db_session_factory()
    # Test is responsible for closing the session'''

content = content.replace(old, new)

with open('tests/conftest.py', 'w') as f:
    f.write(content)
print('Fixed')