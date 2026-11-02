with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix tenant_isolation test - add kind field to decision
old = '''    @pytest.mark.asyncio
    async def test_tenant_isolation(
        self,
        pg_db_session: AsyncSession,
    ):
        """Tenant A changes don't affect Tenant B fingerprint."""
        org_a = Organization(name="Tenant A", slug=f"tenant-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Tenant B", slug=f"tenant-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp_a_before = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_before = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Add decision to tenant A
        decision = CompanyDecision(organization_id=org_a.id, decision_id="DEC-A-001", title="A's Decision", state="proposed")
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp_a_after = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_after = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Tenant A changed
        assert fp_a_before.aggregate_fingerprint != fp_a_after.aggregate_fingerprint
        # Tenant B unchanged
        assert fp_b_before.aggregate_fingerprint == fp_b_after.aggregate_fingerprint'''

new = '''    @pytest.mark.asyncio
    async def test_tenant_isolation(
        self,
        pg_db_session: AsyncSession,
    ):
        """Tenant A changes don't affect Tenant B fingerprint."""
        org_a = Organization(name="Tenant A", slug=f"tenant-a-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Tenant B", slug=f"tenant-b-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp_a_before = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_before = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Add decision to tenant A
        decision = CompanyDecision(organization_id=org_a.id, decision_id="DEC-A-001", kind="strategic", title="A's Decision", state="proposed", fingerprint=_gen_fp())
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp_a_after = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_after = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Tenant A changed
        assert fp_a_before.aggregate_fingerprint != fp_a_after.aggregate_fingerprint
        # Tenant B unchanged
        assert fp_b_before.aggregate_fingerprint == fp_b_after.aggregate_fingerprint'''

content = content.replace(old, new)

# Fix reverse_tenant_isolation test
old2 = '''    @pytest.mark.asyncio
    async def test_reverse_tenant_isolation(
        self,
        pg_db_session: AsyncSession,
    ):
        """Tenant B changes don't affect Tenant A fingerprint."""
        org_a = Organization(name="Tenant A Rev", slug=f"tenant-a-rev-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Tenant B Rev", slug=f"tenant-b-rev-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp_a_before = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_before = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Add decision to tenant B
        decision = CompanyDecision(organization_id=org_b.id, decision_id="DEC-B-001", title="B's Decision", state="proposed")
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp_a_after = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_after = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Tenant B changed
        assert fp_b_before.aggregate_fingerprint != fp_b_after.aggregate_fingerprint
        # Tenant A unchanged
        assert fp_a_before.aggregate_fingerprint == fp_a_after.aggregate_fingerprint'''

new2 = '''    @pytest.mark.asyncio
    async def test_reverse_tenant_isolation(
        self,
        pg_db_session: AsyncSession,
    ):
        """Tenant B changes don't affect Tenant A fingerprint."""
        org_a = Organization(name="Tenant A Rev", slug=f"tenant-a-rev-{uuid.uuid4().hex[:8]}", status="active")
        org_b = Organization(name="Tenant B Rev", slug=f"tenant-b-rev-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add_all([org_a, org_b])
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp_a_before = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_before = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Add decision to tenant B
        decision = CompanyDecision(organization_id=org_b.id, decision_id="DEC-B-001", kind="strategic", title="B's Decision", state="proposed", fingerprint=_gen_fp())
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp_a_after = await service.compute_tenant_fingerprint(pg_db_session, org_a.id)
        fp_b_after = await service.compute_tenant_fingerprint(pg_db_session, org_b.id)
        
        # Tenant B changed
        assert fp_b_before.aggregate_fingerprint != fp_b_after.aggregate_fingerprint
        # Tenant A unchanged
        assert fp_a_before.aggregate_fingerprint == fp_a_after.aggregate_fingerprint'''

content = content.replace(old2, new2)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')