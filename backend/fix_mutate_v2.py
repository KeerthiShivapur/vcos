with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Decision creation
content = content.replace(
    '''decision_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(decision), db.flush(), decision)[2],
            provenance={"source_event_id": decision.source_event_id},
        )''',
    '''async def _create_decision_mutation(db):
            db.add(decision)
            await db.flush()
            return decision

        decision_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=_create_decision_mutation,
            provenance={"source_event_id": decision.source_event_id},
        )''')

# Authorization creation
content = content.replace(
    '''auth_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(auth), db.flush(), auth)[2],
            provenance={"decision_id": decision_id, "policy_id": "default-policy"},
        )''',
    '''async def _create_auth_mutation(db):
            db.add(auth)
            await db.flush()
            return auth

        auth_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=_create_auth_mutation,
            provenance={"decision_id": decision_id, "policy_id": "default-policy"},
        )''')

# Commitment creation
content = content.replace(
    '''commitment_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(commitment), db.flush(), commitment)[2],
            provenance={"authorization_id": authorization_id, "decision_id": decision_id},
        )''',
    '''async def _create_commitment_mutation(db):
            db.add(commitment)
            await db.flush()
            return commitment

        commitment_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            mutation_fn=_create_commitment_mutation,
            provenance={"authorization_id": authorization_id, "decision_id": decision_id},
        )''')

# Action creation
content = content.replace(
    '''action_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyAction",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(action), db.flush(), action)[2],
            provenance={"source_company_decision_id": decision_id, "source_commitment_id": commitment_id, "authorization_id": authorization_id},
        )''',
    '''async def _create_action_mutation(db):
            db.add(action)
            await db.flush()
            return action

        action_result = await canonical_mutation_boundary.mutate(
            db=pg_db_session,
            caller=access,
            target_entity_type="CompanyAction",
            mutation_type=MutationType.CREATE,
            mutation_fn=_create_action_mutation,
            provenance={"source_company_decision_id": decision_id, "source_commitment_id": commitment_id, "authorization_id": authorization_id},
        )''')

# Performance test mutations
content = content.replace(
    '''result = await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                target_entity_type="CompanyDecision",
                mutation_type=MutationType.CREATE,
                mutation_fn=lambda db: (db.add(decision), db.flush(), decision)[2],
                provenance={"source_event_id": f"evt-perf-{i}"},
            )''',
    '''async def _create_perf_decision_mutation(db):
                db.add(decision)
                await db.flush()
                return decision

            result = await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                target_entity_type="CompanyDecision",
                mutation_type=MutationType.CREATE,
                mutation_fn=_create_perf_decision_mutation,
                provenance={"source_event_id": f"evt-perf-{i}"},
            )''')

# Concurrent mutations
content = content.replace(
    '''result = await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                target_entity_type="CompanyDecision",
                mutation_type=MutationType.CREATE,
                mutation_fn=lambda db: (db.add(decision), db.flush(), decision)[2],
                provenance={"source_event_id": f"evt-concurrent-{i}"},
            )''',
    '''async def _create_concurrent_decision_mutation(db):
                db.add(decision)
                await db.flush()
                return decision

            result = await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                target_entity_type="CompanyDecision",
                mutation_type=MutationType.CREATE,
                mutation_fn=_create_concurrent_decision_mutation,
                provenance={"source_event_id": f"evt-concurrent-{i}"},
            )''')

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content)
print('Done')