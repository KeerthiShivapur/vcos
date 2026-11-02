import re

with open('tests/test_gate7_postgres_verification.py', 'r') as f:
    content = f.read()

# Replace setup fixtures to use pg_db_with_tenant
# Pattern: @pytest_asyncio.fixture(autouse=True)\n    async def setup(self, pg_db_session):
# Replace with: @pytest_asyncio.fixture(autouse=True)\n    async def setup(self, pg_db_with_tenant):\n        self.db, self.org_id = pg_db_with_tenant

content_new = content.replace(
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_session):
        self.db = pg_db_session''',
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_with_tenant):
        self.db, self.org_id = pg_db_with_tenant''')

# Also need to handle the case where there's import uuid and org creation
# Remove the org creation code in setup since pg_db_with_tenant handles it
content_new = content

# Remove the org creation code in setup methods
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-lock-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Lock", slug=f"test-lock-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-eo-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org EO", slug=f"test-eo-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-scope-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Scope", slug=f"test-scope-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-temp-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Temp", slug=f"temp-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-prov-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Prov", slug=f"prov-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-contr-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Contr", slug=f"contr-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-fr-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org FR", slug=f"fr-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-bw-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org BW", slug=f"bw-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-perf-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Perf", slug=f"perf-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-long-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Long", slug=f"long-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Also need to update the TestTenantIsolationPostgres class to use pg_db_with_tenant but handle two orgs
# This is more complex - the fixture only creates one org, but the test needs two
# We'll need to create the second org manually but set the context for the first org

# For TestTenantIsolationPostgres, we need special handling since it creates two orgs
# Let's update the setup to use pg_db_with_tenant for the first org, then create the second manually

with open('tests/test_gate7_postgres_verification.py', 'w') as f:
    f.write(content_new)

print('Replacements done')
"