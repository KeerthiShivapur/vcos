with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix failure behavior tests
old = '''@pytest.mark.asyncio
    async def test_missing_required_table_blocks(
        self,
        pg_db_session: AsyncSession,
    ):
        """Missing required component blocks fingerprint."""
        org = Organization(name="Block Corp", slug=f"block-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        # Create custom service with non-existent required table
        custom_components = [
            FingerprintComponent(
                name="nonexistent",
                tables=["this_table_does_not_exist_at_all_xyz"],
                required=True,
            ),
        ]
        
        service = CanonicalFingerprintService()
        
        # Override the component list temporarily
        original = CANONICAL_COMPONENTS
        try:
            import app.services.canonical_fingerprint as cf_module
            cf_module.CANONICAL_COMPONENTS = custom_components
            
            tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
            assert tenant_fp.status == FingerprintStatus.BLOCKED
            assert tenant_fp.error is not None
        finally:
            cf_module.CANONICAL_COMPONENTS = original'''

new = '''@pytest.mark.asyncio
    async def test_missing_required_table_blocks(
        self,
        pg_db_session: AsyncSession,
    ):
        """Missing required component blocks fingerprint."""
        org = Organization(name="Block Corp", slug=f"block-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        # Create custom service with non-existent required table
        custom_components = [
            FingerprintComponent(
                name="nonexistent",
                tables=["this_table_does_not_exist_at_all_xyz"],
                required=True,
            ),
        ]
        
        service = CanonicalFingerprintService()
        
        # Override the component list temporarily
        original = CANONICAL_COMPONENTS
        try:
            import app.services.canonical_fingerprint as cf_module
            cf_module.CANONICAL_COMPONENTS = custom_components
            
            tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
            assert tenant_fp.status == FingerprintStatus.BLOCKED
            assert tenant_fp.error is not None
        finally:
            cf_module.CANONICAL_COMPONENTS = original'''

content = content.replace(old, new)

# Fix secret not in fingerprint test
old2 = '''@pytest.mark.asyncio
    async def test_secret_not_in_fingerprint(
        self,
        pg_db_session: AsyncSession,
    ):
        """Secrets are never included in fingerprint."""
        org = Organization(
            name="Secret Corp",
            slug=f"sec-corp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create connector with secret
        connector = ConnectorInstance(
            organization_id=org.id,
            connector_id="test-connector",
            name="Test Connector",
            configuration_json={"api_key": "secret-key-123", "webhook_secret": "webhook-secret"},
        )
        pg_db_session.add(connector)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Verify the fingerprint doesn't contain the secret
        fp_str = str(tenant_fp.to_dict())
        assert "secret-key-123" not in fp_str
        assert "webhook-secret" not in fp_str'''

new2 = '''@pytest.mark.asyncio
    async def test_secret_not_in_fingerprint(
        self,
        pg_db_session: AsyncSession,
    ):
        """Secrets are never included in fingerprint."""
        org = Organization(
            name="Secret Corp",
            slug=f"sec-corp-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        pg_db_session.add(org)
        await pg_db_session.flush()
        
        # Create connector with secret
        from app.models.canonical_integration import ConnectorInstance
        connector = ConnectorInstance(
            organization_id=org.id,
            connector_id="test-connector",
            name="Test Connector",
            config_json={"api_key": "secret-key-123", "webhook_secret": "webhook-secret"},
        )
        pg_db_session.add(connector)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService()
        tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        # Verify the fingerprint doesn't contain the secret
        fp_str = str(tenant_fp.to_dict())
        assert "secret-key-123" not in fp_str
        assert "webhook-secret" not in fp_str'''

content = content.replace(old2, new2)

# Fix fingerprint algorithm test
old3 = '''@pytest.mark.asyncio
    async def test_sha256_64_algorithm(
        self,
        pg_db_session: AsyncSession,
    ):
        """SHA256_64 produces 64-char fingerprints."""
        org = Organization(name="Algo Corp", slug=f"algo-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService(algorithm=FingerprintAlgorithm.SHA256_64)
        tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert len(tenant_fp.aggregate_fingerprint) == 64
        for comp in tenant_fp.components:
            assert len(comp.fingerprint) == 64
            assert comp.algorithm == FingerprintAlgorithm.SHA256_64'''

new3 = '''@pytest.mark.asyncio
    async def test_sha256_64_algorithm(
        self,
        pg_db_session: AsyncSession,
    ):
        """SHA256_64 produces 64-char fingerprints."""
        org = Organization(name="Algo Corp", slug=f"algo-corp-{uuid.uuid4().hex[:8]}", status="active")
        pg_db_session.add(org)
        await pg_db_session.commit()
        
        service = CanonicalFingerprintService(algorithm=FingerprintAlgorithm.SHA256_64)
        tenant_fp = await service.compute_tenant_fingerprint(pg_db_session, org.id)
        
        assert len(tenant_fp.aggregate_fingerprint) == 64
        for comp in tenant_fp.components:
            assert len(comp.fingerprint) == 64
            assert comp.algorithm == FingerprintAlgorithm.SHA256_64'''

content = content.replace(old3, new3)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')