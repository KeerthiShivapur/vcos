with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix aggregate_changes_with_data test - add kind field to decision
old = '''    @pytest.mark.asyncio
    async def test_aggregate_changes_with_data(
        self,
        pg_db_session: AsyncSession,
    ):
        """Aggregate fingerprint changes when canonical data changes."""
        org = Organization(name="Aggregate Corp", slug=f"agg-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Add a decision
        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="DEC-001",
            title="Test Decision",
            state="proposed",
        )
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint
        # The decisions component should show the change
        dec_comp_1 = next((c for c in fp1.components if c.component_name == "decisions"), None)
        dec_comp_2 = next((c for c in fp2.components if c.component_name == "decisions"), None)
        assert dec_comp_1 is not None and dec_comp_2 is not None
        assert dec_comp_1.fingerprint != dec_comp_2.fingerprint
        assert dec_comp_2.entity_count > dec_comp_1.entity_count'''

new = '''    @pytest.mark.asyncio
    async def test_aggregate_changes_with_data(
        self,
        pg_db_session: AsyncSession,
    ):
        """Aggregate fingerprint changes when canonical data changes."""
        org = Organization(name="Aggregate Corp", slug=f"agg-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        
        fp1 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Add a decision
        decision = CompanyDecision(
            organization_id=org.id,
            decision_id="DEC-001",
            kind="strategic",
            title="Test Decision",
            state="proposed",
            fingerprint=_gen_fp(),
        )
        pg_db_session.add(decision)
        await pg_db_session.commit()
        
        fp2 = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert fp1.aggregate_fingerprint != fp2.aggregate_fingerprint
        # The decisions component should show the change
        dec_comp_1 = next((c for c in fp1.components if c.component_name == "decisions"), None)
        dec_comp_2 = next((c for c in fp2.components if c.component_name == "decisions"), None)
        assert dec_comp_1 is not None and dec_comp_2 is not None
        assert dec_comp_1.fingerprint != dec_comp_2.fingerprint
        assert dec_comp_2.entity_count > dec_comp_1.entity_count'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')