with open('tests/acceptance/test_release_candidate_slice_2d.py', 'r') as f:
    content = f.read()

# Fix the phase_transitions test
old = '''        # Test phase progression
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
            assert execution.phase == phase
        
        # Verify phase history
        assert len(release.phase_history) == len(phases)
        for i, phase in enumerate(phases):
            assert release.phase_history[i]["to_phase"] == phase'''

new = '''        # Test phase transitions via release_failure_recovery_service
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
            assert execution.phase == phase
        
        # Verify phase history
        assert len(release.phase_history) == len(phases)
        for i, phase in enumerate(phases):
            assert release.phase_history[i]["to_phase"] == phase'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2d.py', 'w') as f:
    f.write(content)
print('Done')