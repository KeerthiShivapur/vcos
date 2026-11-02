#!/usr/bin/env python3
"""Fix the test_org fixture - move to module level properly."""

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    content = f.read()

# The fixture starts at line 471-494 (0-indexed: 470-493)
# Find the exact text
fixture_text = '''    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession):
        """Create a test organization with some data."""
        org = Organization(
            name=f"Test Integrity Org {uuid.uuid4().hex[:8]}",
            slug=f"test-org-{uuid.uuid4().hex[:8]}",
            industry="Software",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()

        user = User(
            organization_id=org.id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hashed_password",
        )
        db_session.add(user)
        await db_session.flush()

        return {"org": org, "user": user}

'''

# Remove the fixture from the class
content = content.replace(fixture_text, '')

# Now add it at module level (after imports, before first class)
# Find first class
first_class = content.find('class TestReliabilityVocabularies:')
if first_class != -1:
    # The fixture at module level (no self, proper indentation)
    module_fixture = '''@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession):
    """Create a test organization with some data."""
    org = Organization(
        name=f"Test Integrity Org {uuid.uuid4().hex[:8]}",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
        industry="Software",
        country="US",
        timezone="UTC",
        currency="USD",
    )
    db_session.add(org)
    await db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Test User",
        password_hash="hashed_password",
    )
    db_session.add(user)
    await db_session.flush()

    return {"org": org, "user": user}

'''
    content = content[:first_class] + module_fixture + '\n' + content[first_class:]

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.write(content)

print('Fixed fixture')