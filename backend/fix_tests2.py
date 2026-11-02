import re

with open('tests/test_gate7_postgres_verification.py', 'r') as f:
    content = f.read()

# Replace setup fixtures to use pg_db_with_tenant
content_new = content.replace(
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_session):
        self.db = pg_db_session''',
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_with_tenant):
        self.db, self.org_id = pg_db_with_tenant''')

# Remove the org creation code in setup methods
content_new = content.replace(
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
        org_id = f"test-org-piv-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org PIV", slug=f"piv-{uuid.uuid4().hex[:8]}", status="active")
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

# Update TestTenantIsolationPostgres to use pg_db_with_tenant
content_new = content_new.replace(
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_session):
        self.db = pg_db_session
        import uuid
        
        # Create Org A
        org_a_id = f"org-a-{uuid.uuid4().hex[:8]}"
        org_a = Organization(id=org_a_id, name="Org A", slug=f"org-a-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_a); await self.db.flush()
        self.org_a_id = org_a_id
        
        # Create Org B
        org_b_id = f"org-b-{uuid.uuid4().hex[:8]}"
        org_b = Organization(id=org_b_id, name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_b); await self.db.flush()
        self.org_b_id = org_b_id
        
        await self.db.commit()''',
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_with_tenant):
        self.db, self.org_a_id = pg_db_with_tenant
        
        # Create Org B manually
        import uuid
        org_b_id = f"org-b-{uuid.uuid4().hex[:8]}"
        org_b = Organization(id=org_b_id, name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_b); await self.db.flush()
        self.org_b_id = org_b_id
        
        await self.db.commit()''')

# Update TestScopeIsolation
content_new = content_new.replace(
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_session):
        self.db = pg_db_session
        import uuid
        org_id = f"test-org-scope-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Scope", slug=f"test-scope-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_with_tenant):
        self.db, self.org_id = pg_db_with_tenant''')

# Update TestTemporalTruthPostgres
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-temp-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Temp", slug=f"temp-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestProvenanceIntegrity
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-prov-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Prov", slug=f"prov-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestContradictionPreservationPostgres (first occurrence)
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-prov-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Prov", slug=f"prov-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestContradictionPreservationPostgres (second occurrence)
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-contr-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Contr", slug=f"contr-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestFailureRecovery
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-fr-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org FR", slug=f"fr-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestBackgroundWorkerCorrectness
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-bw-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org BW", slug=f"bw-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestPostgresPerformance
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-perf-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Perf", slug=f"perf-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestProductionIntegrityVerifier
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-piv-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org PIV", slug=f"piv-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestLongitudinalCompanyOperation
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-long-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Long", slug=f"long-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestTenantIsolationPostgres to use pg_db_with_tenant
content_new = content_new.replace(
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_session):
        self.db = pg_db_session
        import uuid
        
        # Create Org A
        org_a_id = f"org-a-{uuid.uuid4().hex[:8]}"
        org_a = Organization(id=org_a_id, name="Org A", slug=f"org-a-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_a); await self.db.flush()
        self.org_a_id = org_a_id
        
        # Create Org B
        org_b_id = f"org-b-{uuid.uuid4().hex[:8]}"
        org_b = Organization(id=org_b_id, name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_b); await self.db.flush()
        self.org_b_id = org_b_id
        
        await self.db.commit()''',
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_with_tenant):
        self.db, self.org_a_id = pg_db_with_tenant
        
        # Create Org B manually
        import uuid
        org_b_id = f"org-b-{uuid.uuid4().hex[:8]}"
        org_b = Organization(id=org_b_id, name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_b); await self.db.flush()
        self.org_b_id = org_b_id
        
        await self.db.commit()''')

# Update TestScopeIsolation
content_new = content_new.replace(
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_session):
        self.db = pg_db_session
        import uuid
        org_id = f"test-org-scope-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Scope", slug=f"test-scope-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_with_tenant):
        self.db, self.org_id = pg_db_with_tenant''')

# Update TestTemporalTruthPostgres
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-temp-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Temp", slug=f"temp-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestProvenanceIntegrity
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-prov-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Prov", slug=f"prov-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestContradictionPreservationPostgres (first occurrence)
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-prov-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Prov", slug=f"prov-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestContradictionPreservationPostgres (second occurrence)
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-contr-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Contr", slug=f"contr-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestFailureRecovery
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-fr-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org FR", slug=f"fr-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestBackgroundWorkerCorrectness
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-bw-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org BW", slug=f"bw-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestPostgresPerformance
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-perf-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Perf", slug=f"perf-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestProductionIntegrityVerifier
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-piv-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org PIV", slug=f"piv-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestLongitudinalCompanyOperation
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-long-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Long", slug=f"long-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestTenantIsolationPostgres to use pg_db_with_tenant
content_new = content_new.replace(
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_session):
        self.db = pg_db_session
        import uuid
        
        # Create Org A
        org_a_id = f"org-a-{uuid.uuid4().hex[:8]}"
        org_a = Organization(id=org_a_id, name="Org A", slug=f"org-a-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_a); await self.db.flush()
        self.org_a_id = org_a_id
        
        # Create Org B
        org_b_id = f"org-b-{uuid.uuid4().hex[:8]}"
        org_b = Organization(id=org_b_id, name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_b); await self.db.flush()
        self.org_b_id = org_b_id
        
        await self.db.commit()''',
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_with_tenant):
        self.db, self.org_a_id = pg_db_with_tenant
        
        # Create Org B manually
        import uuid
        org_b_id = f"org-b-{uuid.uuid4().hex[:8]}"
        org_b = Organization(id=org_b_id, name="Org B", slug=f"org-b-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org_b); await self.db.flush()
        self.org_b_id = org_b_id
        
        await self.db.commit()''')

# Update TestScopeIsolation
content_new = content_new.replace(
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_session):
        self.db = pg_db_session
        import uuid
        org_id = f"test-org-scope-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Scope", slug=f"test-scope-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, pg_db_with_tenant):
        self.db, self.org_id = pg_db_with_tenant''')

# Update TestTemporalTruthPostgres
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-temp-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Temp", slug=f"temp-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestProvenanceIntegrity
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-prov-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Prov", slug=f"prov-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestContradictionPreservationPostgres (first occurrence)
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-prov-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Prov", slug=f"prov-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestContradictionPreservationPostgres (second occurrence)
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-contr-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Contr", slug=f"contr-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestFailureRecovery
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-fr-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org FR", slug=f"fr-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestBackgroundWorkerCorrectness
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-bw-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org BW", slug=f"bw-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestPostgresPerformance
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-perf-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Perf", slug=f"perf-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestProductionIntegrityVerifier
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-piv-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org PIV", slug=f"piv-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

# Update TestLongitudinalCompanyOperation
content_new = content_new.replace(
    '''        import uuid
        org_id = f"test-org-long-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Test Org Long", slug=f"long-{uuid.uuid4().hex[:8]}", status="active")
        self.db.add(org); await self.db.flush()
        await self.db.commit()
        self.org_id = org_id''',
    '''        # Organization and org_id are provided by pg_db_with_tenant fixture
        pass''')

with open('tests/test_gate7_postgres_verification.py', 'w') as f:
    f.write(content_new)
print('Replacements done')