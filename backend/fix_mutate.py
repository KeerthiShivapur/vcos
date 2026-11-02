with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Fix all mutate calls
# Decision creation
content = content.replace(
    '''decision_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            entity=decision,
            provenance={"source_event_id": decision.source_event_id},
        )''',
    '''decision_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(decision), db.flush(), decision)[2],
            provenance={"source_event_id": decision.source_event_id},
        )''')

# Authorization creation
content = content.replace(
    '''auth_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            entity=auth,
            provenance={"decision_id": decision_id, "policy_id": "default-policy"},
        )''',
    '''auth_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(auth), db.flush(), auth)[2],
            provenance={"decision_id": decision_id, "policy_id": "default-policy"},
        )''')

# Commitment creation
content = content.replace(
    '''commitment_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            entity=commitment,
            provenance={"authorization_id": authorization_id, "decision_id": decision_id},
        )''',
    '''commitment_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(commitment), db.flush(), commitment)[2],
            provenance={"authorization_id": authorization_id, "decision_id": decision_id},
        )''')

# Action creation
content = content.replace(
    '''action_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            entity=action,
            provenance={"source_company_decision_id": decision_id, "source_commitment_id": commitment_id, "authorization_id": authorization_id},
        )''',
    '''action_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyAction",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(action), db.flush(), action)[2],
            provenance={"source_company_decision_id": decision_id, "source_commitment_id": commitment_id, "authorization_id": authorization_id},
        )''')

# Performance test mutations
content = content.replace(
    '''result = await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                entity=decision,
                provenance={"source_event_id": f"evt-perf-{i}"},
            )''',
    '''result = await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                target_entity_type="CompanyDecision",
                mutation_type=MutationType.CREATE,
                mutation_fn=lambda db: (db.add(decision), db.flush(), decision)[2],
                provenance={"source_event_id": f"evt-perf-{i}"},
            )''')

# Concurrent mutations
content = content.replace(
    '''result = await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                entity=decision,
                provenance={"source_event_id": f"evt-concurrent-{i}"},
            )''',
    '''result = await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                target_entity_type="CompanyDecision",
                mutation_type=MutationType.CREATE,
                mutation_fn=lambda db: (db.add(decision), db.flush(), decision)[2],
                provenance={"source_event_id": f"evt-concurrent-{i}"},
            )''')

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content)
print('Done')