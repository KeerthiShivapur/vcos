import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the autonomy proposal creation to use mutation_fn pattern
old_autonomy = '''        proposal_result = await canonical_mutation_boundary.mutate(
            db_session,
            access,
            target_entity_type="AutonomyProposal",
            mutation_type=MutationType.CREATE,
            entity=proposal,
        )'''

new_autonomy = '''        async def create_proposal_fn(db):
            db.add(proposal)
            await db.flush()
            return proposal
        
        proposal_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="AutonomyProposal",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_proposal_fn,
            provenance={"actor_id": access.employee_id},
        )'''

if old_autonomy in content:
    content = content.replace(old_autonomy, new_autonomy)
    print('Fixed autonomy proposal mutation')
else:
    print('Block not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')