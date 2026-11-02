with open('tests/conftest.py', 'r') as f:
    content = f.read()

# Fix the pg_db_session fixture
old = '''@pytest_asyncio.fixture(scope="function")
async def pg_db_session(pg_db_session_factory):
    """Individual test session - test manages its own lifecycle."""
    session = pg_db_session_factory()
    session.expire_on_commit = False
    yield session
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
    
    yield session
    # Test is responsible for closing the session'''

content = content.replace(old, new)

with open('tests/conftest.py', 'w') as f:
    f.write(content)
print('Fixed')