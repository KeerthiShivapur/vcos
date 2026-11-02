with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix release candidate fingerprint tests
old = '''@pytest.mark.asyncio
    async def test_create_release_candidate_fingerprint(
        self,
        pg_db_session: AsyncSession,
    ):
        """Release candidate fingerprint captures all tenants."""
        org_a = Organization(name="RCA", slug=f"rc-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="RCB", slug=f"rc-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        
        # Add some data
        dec = CompanyDecision(organization_id=org_a.id, decision_id="DEC-1", title="A Dec", state="approved")
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        rc_fp = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id=f"rc-{uuid.uuid4().hex[:8]}",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        assert len(rc_fp.tenants) == 2
        assert rc_fp.application_version == "1.0.0"
        assert rc_fp.schema_revision == "head"
        
        # Each tenant has components
        for tenant in rc_fp.tenants:
            assert len(tenant.components) > 0
            assert tenant.aggregate_fingerprint
            assert tenant.status == FingerprintStatus.COMPUTED'''

new = '''@pytest.mark.asyncio
    async def test_create_release_candidate_fingerprint(
        self,
        pg_db_session: AsyncSession,
    ):
        """Release candidate fingerprint captures all tenants."""
        org_a = Organization(name="RCA", slug=f"rc-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="RCB", slug=f"rc-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        
        # Add some data
        dec = CompanyDecision(organization_id=org_a.id, decision_id="DEC-1", kind="strategic", title="A Dec", state="approved", fingerprint=_gen_fp())
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        rc_fp = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id=f"rc-{uuid.uuid4().hex[:8]}",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        assert len(rc_fp.tenants) == 2
        assert rc_fp.application_version == "1.0.0"
        assert rc_fp.schema_revision == "head"
        
        # Each tenant has components
        for tenant in rc_fp.tenants:
            assert len(tenant.components) > 0
            assert tenant.aggregate_fingerprint
            assert tenant.status == FingerprintStatus.COMPUTED'''

content = content.replace(old, new)

# Fix fingerprint comparison match test
old2 = '''@pytest.mark.asyncio
    async def test_fingerprint_comparison_match(
        self,
        pg_db_session: AsyncSession,
    ):
        """Identical fingerprints compare as MATCH."""
        org = Organization(name="Compare Corp", slug=f"cmp-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MATCH"'''

new2 = '''@pytest.mark.asyncio
    async def test_fingerprint_comparison_match(
        self,
        pg_db_session: AsyncSession,
    ):
        """Identical fingerprints compare as MATCH."""
        org = Organization(name="Compare Corp", slug=f"cmp-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MATCH"'''

content = content.replace(old2, new2)

# Fix fingerprint comparison mismatch test
old3 = '''@pytest.mark.asyncio
    async def test_fingerprint_comparison_mismatch(
        self,
        pg_db_session: AsyncSession,
    ):
        """Different canonical state detected as MISMATCH."""
        org_a = Organization(name="Org A", slug=f"cmp-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Org B", slug=f"cmp-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        
        # Only org_a has a decision
        dec = CompanyDecision(organization_id=org_a.id, decision_id="DEC-1", title="Decision", state="approved")
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
            organization_ids=[org_a.id],  # Only one org
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MISMATCH"'''

new3 = '''@pytest.mark.asyncio
    async def test_fingerprint_comparison_mismatch(
        self,
        pg_db_session: AsyncSession,
    ):
        """Different canonical state detected as MISMATCH."""
        org_a = Organization(name="Org A", slug=f"cmp-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Org B", slug=f"cmp-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        
        # Only org_a has a decision
        dec = CompanyDecision(organization_id=org_a.id, decision_id="DEC-1", kind="strategic", title="Decision", state="approved", fingerprint=_gen_fp())
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
            organization_ids=[org_a.id],  # Only one org
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MISMATCH"'''

content = content.replace(old3, new3)

# Fix component level diff test
old4 = '''@pytest.mark.asyncio
    async def test_component_level_diff(
        self,
        pg_db_session: AsyncSession,
    ):
        """Component-level differences are identified."""
        org = Organization(name="Diff Corp", slug=f"diff-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        # Add decision
        dec = CompanyDecision(organization_id=org.id, decision_id="DEC-NEW", title="New Decision", state="approved")
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MISMATCH"
        assert len(result["component_differences"]) > 0
        diff = result["component_differences"][0]
        assert diff["component"] == "decisions"'''

new4 = '''@pytest.mark.asyncio
    async def test_component_level_diff(
        self,
        pg_db_session: AsyncSession,
    ):
        """Component-level differences are identified."""
        org = Organization(name="Diff Corp", slug=f"diff-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = ReleaseCandidateFingerprintService()
        
        fp1 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-1",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        # Add decision
        dec = CompanyDecision(organization_id=org.id, decision_id="DEC-NEW", kind="strategic", title="New Decision", state="approved", fingerprint=_gen_fp())
        pg_db_session.add(dec)
        await pg_db_session.commit()
        
        fp2 = await service.create_release_candidate_fingerprint(
            db=pg_db_session,
            release_candidate_id="rc-2",
            application_version="1.0.0",
            schema_revision="head",
        )
        
        result = await service.compare_fingerprints(fp1, fp2)
        assert result["overall"] == "MISMATCH"
        assert len(result["component_differences"]) > 0
        diff = result["component_differences"][0]
        assert diff["component"] == "decisions"'''

content = content.replace(old4, new4)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')