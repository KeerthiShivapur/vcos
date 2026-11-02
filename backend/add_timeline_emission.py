with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Add _emit_canonical_timeline_event to imports if not present
if '_emit_canonical_timeline_event' not in content:
    idx = content.find('from app.intelligence.canonical_mutation import')
    if idx >= 0:
        line_end = content.find('\n', idx)
        content = content[:line_end] + ', _emit_canonical_timeline_event' + content[line_end:]

# Decision creation
content = content.replace(
    '''assert decision_result.success, f"Decision creation failed: {decision_result.error}"
        decision_id = decision_result.entity.id''',
    '''assert decision_result.success, f"Decision creation failed: {decision_result.error}"
        decision_id = decision_result.entity.id
        # Emit timeline event for CREATE
        await _emit_canonical_timeline_event(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            target_id=decision_id,
            entity=decision_result.entity,
            source_event_id=decision.source_event_id,
            provenance={},
        )''')

# Authorization creation
content = content.replace(
    '''assert auth_result.success, f"Authorization creation failed: {auth_result.error}"
        authorization_id = auth_result.entity.id''',
    '''assert auth_result.success, f"Authorization creation failed: {auth_result.error}"
        authorization_id = auth_result.entity.id
        # Emit timeline event for CREATE
        await _emit_canonical_timeline_event(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            target_id=authorization_id,
            entity=auth_result.entity,
            source_event_id=auth.source_event_id,
            provenance={},
        )''')

# Commitment creation
content = content.replace(
    '''assert commitment_result.success, f"Commitment creation failed: {commitment_result.error}"
        commitment_id = commitment_result.entity.id''',
    '''assert commitment_result.success, f"Commitment creation failed: {commitment_result.error}"
        commitment_id = commitment_result.entity.id
        # Emit timeline event for CREATE
        await _emit_canonical_timeline_event(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            target_id=commitment_id,
            entity=commitment_result.entity,
            source_event_id=commitment.source_event_id,
            provenance={},
        )''')

# Action creation - note the original has "action = result.entity"
content = content.replace(
    '''assert action_result.success, f"Action creation failed: {action_result.error}"
        action = result.entity''',
    '''assert action_result.success, f"Action creation failed: {action_result.error}"
        action = action_result.entity
        # Emit timeline event for CREATE
        await _emit_canonical_timeline_event(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyAction",
            mutation_type=MutationType.CREATE,
            target_id=action.id,
            entity=action,
            source_event_id=action.source_event_id,
            provenance={},
        )''')

# Performance test mutations
content = content.replace(
    '''assert result.success
        elapsed = time.perf_counter() - start''',
    '''assert result.success
        # Emit timeline event for CREATE
        await _emit_canonical_timeline_event(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            target_id=result.entity.id,
            entity=result.entity,
            source_event_id=f"evt-perf-{i}",
            provenance={},
        )
        elapsed = time.perf_counter() - start''')

# Concurrent mutations
content = content.replace(
    '''assert result.success
                elapsed = time.perf_counter() - start''',
    '''assert result.success
                # Emit timeline event for CREATE
                await _emit_canonical_timeline_event(
                    db=pg_db_session,
                    caller=access,
                    target_entity_type="CompanyDecision",
                    mutation_type=MutationType.CREATE,
                    target_id=result.entity.id,
                    entity=result.entity,
                    source_event_id=f"evt-concurrent-{i}",
                    provenance={},
                )
                elapsed = time.perf_counter() - start''')

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content)
print('Done')