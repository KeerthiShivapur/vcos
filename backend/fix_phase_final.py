with open('tests/acceptance/test_release_candidate_slice_2d.py', 'r') as f:
    content = f.read()

# Find and replace the test_phase_transitions method
old = '''    @pytest.mark.asyncio
    async def test_phase_transitions(
        self,
        pg_db_session: AsyncSession,
        test_org: Organization,
    ):
        """Test deployment phase transitions."""
        orchestrator = ReleaseDeploymentOrchestrator()
        execution = await orchestrator.create_deployment_plan(
            db=pg_db_session,
            version="1.0.0",
            organization_id=test_org.id,
            initiated_by="test-user",
        )
        
        # Test phase progression
        phases = [
            "preparing",
            "preflight_validation",
            "fingerprint_capture",
            "backup_creation",
            "migration_execution",
            "application_deployment",
            "post_deployment_validation",
            "canonical_verification",
            "active",
        ]
        
        for phase in phases:
            execution = await orchestrator.advance_phase(
                db=pg_db_session,
                release_id=execution.id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert execution.phase == phase'''

new = '''    @pytest.mark.asyncio
    async def test_phase_transitions(
        self,
        pg_db_session: AsyncSession,
        test_org: Organization,
    ):
        """Test release phase transitions via recovery service."""
        from app.services.release_failure_recovery import release_failure_recovery_service
        
        orchestrator = ReleaseDeploymentOrchestrator()
        execution = await orchestrator.create_deployment_plan(
            db=pg_db_session,
            version="1.0.0",
            organization_id=test_org.id,
            initiated_by="test-user",
        )
        
        # Test phase progression via recovery service
        phases = [
            "preflight_validation",
            "fingerprint_capture",
            "backup_creation",
            "migration_execution",
            "application_deployment",
            "post_deployment_validation",
            "canonical_verification",
            "active",
        ]
        
        for phase in phases:
            execution = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=execution.id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert execution.phase == phase'''

content = content.replace(
    '''    @pytest.mark.asyncio
    async def test_phase_transitions(
        self,
        pg_db_session: AsyncSession,
        test_org: Organization,
    ):
        """Test deployment phase transitions."""
        orchestrator = ReleaseDeploymentOrchestrator()
        execution = await orchestrator.create_deployment_plan(
            db=pg_db_session,
            version="1.0.0",
            organization_id=test_org.id,
            initiated_by="test-user",
        )
        
        # Test phase progression
        phases = [
            "preparing",
            "preflight_validation",
            "fingerprint_capture",
            "backup_creation",
            "migration_execution",
            "application_deployment",
            "post_deployment_validation",
            "canonical_verification",
            "active",
        ]
        
        for phase in phases:
            execution = await orchestrator.advance_phase(
                db=pg_db_session,
                release_id=execution.id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert execution.phase == phase''',
    '''    @pytest.mark.asyncio
    async def test_phase_transitions(
        self,
        pg_db_session: AsyncSession,
        test_org: Organization,
    ):
        """Test release phase transitions via recovery service."""
        from app.services.release_failure_recovery import release_failure_recovery_service
        
        orchestrator = ReleaseDeploymentOrchestrator()
        execution = await orchestrator.create_deployment_plan(
            db=pg_db_session,
            version="1.0.0",
            organization_id=test_org.id,
            initiated_by="test-user",
        )
        
        # Test phase progression via recovery service
        phases = [
            "preflight_validation",
            "fingerprint_capture",
            "backup_creation",
            "migration_execution",
            "application_deployment",
            "post_deployment_validation",
            "canonical_verification",
            "active",
        ]
        
        for phase in phases:
            execution = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=execution.id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert execution.phase == phase''')

with open('tests/acceptance/test_release_candidate_slice_2d.py', 'w') as f:
    f.write(content)
print('Done')