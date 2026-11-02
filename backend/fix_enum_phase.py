with open('tests/acceptance/test_release_candidate_slice_2d.py', 'r') as f:
    content = f.read()

old = '''    @pytest.mark.asyncio
    async def test_phase_transitions(
        self,
        pg_db_session: AsyncSession,
        test_org: Organization,
    ):
        """Test release phase transitions via recovery service."""
        from app.services.release_failure_recovery import release_failure_recovery_service
        from app.models.release import ReleaseRecord
        
        # Create a ReleaseRecord for phase transition testing
        release_record = ReleaseRecord(
            id=f"rel-{uuid.uuid4().hex[:12]}",
            organization_id=test_org.id,
            version="1.0.0",
            status="pending",
            phase=ReleasePhase.PLANNED.value,
            initiated_by="test-user",
        )
        pg_db_session.add(release_record)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
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
        
        release_id = release_record.id
        
        for phase in phases:
            release_record = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=release_id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert release_record.phase == phase'''

new = '''    @pytest.mark.asyncio
    async def test_phase_transitions(
        self,
        pg_db_session: AsyncSession,
        test_org: Organization,
    ):
        """Test release phase transitions via recovery service."""
        from app.services.release_failure_recovery import release_failure_recovery_service
        from app.models.release import ReleaseRecord, ReleasePhase
        
        # Create a ReleaseRecord for phase transition testing
        release_record = ReleaseRecord(
            id=f"rel-{uuid.uuid4().hex[:12]}",
            organization_id=test_org.id,
            version="1.0.0",
            status="pending",
            phase=ReleasePhase.PLANNED.value,
            initiated_by="test-user",
        )
        pg_db_session.add(release_record)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        # Test phase progression via recovery service
        phases = [
            ReleasePhase.PREFLIGHT_VALIDATION,
            ReleasePhase.FINGERPRINT_CAPTURE,
            ReleasePhase.BACKUP_CREATION,
            ReleasePhase.MIGRATION_EXECUTION,
            ReleasePhase.APPLICATION_DEPLOYMENT,
            ReleasePhase.POST_DEPLOYMENT_VALIDATION,
            ReleasePhase.CANAONICAL_VERIFICATION,
            ReleasePhase.ACTIVE,
        ]
        
        release_id = release_record.id
        
        for phase in phases:
            release_record = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=release_id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert release_record.phase == phase.value'''

content = content.replace(
    '''    @pytest.mark.asyncio
    async def test_phase_transitions(
        self,
        pg_db_session: AsyncSession,
        test_org: Organization,
    ):
        """Test release phase transitions via recovery service."""
        from app.services.release_failure_recovery import release_failure_recovery_service
        from app.models.release import ReleaseRecord
        
        # Create a ReleaseRecord for phase transition testing
        release_record = ReleaseRecord(
            id=f"rel-{uuid.uuid4().hex[:12]}",
            organization_id=test_org.id,
            version="1.0.0",
            status="pending",
            phase=ReleasePhase.PLANNED.value,
            initiated_by="test-user",
        )
        pg_db_session.add(release_record)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
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
        
        release_id = release_record.id
        
        for phase in phases:
            release_record = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=release_id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert release_record.phase == phase''',
    '''    @pytest.mark.asyncio
    async def test_phase_transitions(
        self,
        pg_db_session: AsyncSession,
        test_org: Organization,
    ):
        """Test release phase transitions via recovery service."""
        from app.services.release_failure_recovery import release_failure_recovery_service
        from app.models.release import ReleaseRecord, ReleasePhase
        
        # Create a ReleaseRecord for phase transition testing
        release_record = ReleaseRecord(
            id=f"rel-{uuid.uuid4().hex[:12]}",
            organization_id=test_org.id,
            version="1.0.0",
            status="pending",
            phase=ReleasePhase.PLANNED.value,
            initiated_by="test-user",
        )
        pg_db_session.add(release_record)
        await pg_db_session.flush()
        await pg_db_session.commit()
        
        # Test phase progression via recovery service
        phases = [
            ReleasePhase.PREFLIGHT_VALIDATION,
            ReleasePhase.FINGERPRINT_CAPTURE,
            ReleasePhase.BACKUP_CREATION,
            ReleasePhase.MIGRATION_EXECUTION,
            ReleasePhase.APPLICATION_DEPLOYMENT,
            ReleasePhase.POST_DEPLOYMENT_VALIDATION,
            ReleasePhase.CANAONICAL_VERIFICATION,
            ReleasePhase.ACTIVE,
        ]
        
        release_id = release_record.id
        
        for phase in phases:
            release_record = await release_failure_recovery_service.advance_phase(
                db=pg_db_session,
                release_id=release_id,
                new_phase=phase,
                actor_id="test-user",
            )
            assert release_record.phase == phase.value''')

with open('tests/acceptance/test_release_candidate_slice_2d.py', 'w') as f:
    f.write(content)
print('Done')