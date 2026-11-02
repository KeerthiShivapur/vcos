import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the action creation to use mutation_fn with provenance
old_action_mutate = '''        action_result = await canonical_mutation_boundary.mutate(
            db_session,
            access,
            target_entity_type="CompanyAction",
            mutation_type=MutationType.CREATE,
            entity=action,
        )'''

new_action_mutate = '''        async def create_action_fn(db):
            db.add(action)
            await db.flush()
            return action
        
        action_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAction",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_action_fn,
            provenance={"source_company_decision_id": decision_id, "source_commitment_id": commitment_id, "source_scenario_id": None},
        )'''

if old_action_mutate in content:
    content = content.replace(old_action_mutate, new_action_mutate)
    print('Fixed action mutation')
else:
    print('Block not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')