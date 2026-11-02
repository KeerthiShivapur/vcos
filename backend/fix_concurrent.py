with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Fix the concurrent mutations section
old_code = '''            return await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                entity=decision,
                provenance={"source_event_id": f"evt-concurrent-{i}"},
            )'''

new_code = '''            async def _create_concurrent_decision_mutation(db):
                db.add(decision)
                await db.flush()
                return decision
            
            return await canonical_mutation_boundary.mutate(
                db=pg_db_session,
                caller=access,
                target_entity_type="CompanyDecision",
                mutation_type=MutationType.CREATE,
                mutation_fn=_create_concurrent_decision_mutation,
                provenance={"source_event_id": f"evt-concurrent-{i}"},
            )'''

content = content.replace(old_code, new_code)
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content)
print('Done')