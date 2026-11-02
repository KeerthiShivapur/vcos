with open('tests/test_gate6g_exact_once_concurrency.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the regression test - remove duplicate transition to pending_authorization
old_regression = '''        # Update through states
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            updates={"state": "pending_authorization"},
            provenance={"authorization_id": "auth-reg", "decision_id": "dec-reg"},
            required_permissions=["commitments:manage"],
        )
        
        assert result.success is True
        
        # Transition to authorized
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            new_state="pending_authorization",
            provenance={"authorization_id": "auth-reg", "decision_id": "dec-reg"},
            required_permissions=["commitments:manage"],
        )
        
        assert result.success is True
        
        # Transition to authorized
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            new_state="authorized",
            provenance={"authorization_id": "auth-reg", "decision_id": "dec-reg"},
            required_permissions=["commitments:manage"],
        )'''

new_regression = '''        # Update through states
        result = await canonical_update(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            updates={"state": "pending_authorization"},
            provenance={"authorization_id": "auth-reg", "decision_id": "dec-reg"},
            required_permissions=["commitments:manage"],
        )
        
        assert result.success is True
        
        # Transition to authorized (not pending_authorization again)
        result = await canonical_transition(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyCommitment",
            entity_id=comm.id,
            new_state="authorized",
            provenance={"authorization_id": "auth-reg", "decision_id": "dec-reg"},
            required_permissions=["commitments:manage"],'''

content = content.replace(old_regression, new_regression)

with open('tests/test_gate6g_exact_once_concurrency.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed regression test')