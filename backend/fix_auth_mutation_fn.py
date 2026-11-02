import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the authorization mutation function - the lambda is not async
old_auth_fn = '''        auth_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(authorization), db.flush(), authorization)[2],
            provenance={"decision_id": decision_id, "policy_id": "default-policy"},
        )'''

new_auth_fn = '''        async def create_auth_fn(db):
            db.add(authorization)
            await db.flush()
            return authorization
        
        auth_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_auth_fn,
            provenance={"decision_id": decision_id, "policy_id": "default-policy"},
        )'''

if old_auth_fn in content:
    content = content.replace(old_auth_fn, new_auth_fn)
    print('Fixed authorization mutation function')
else:
    print('Block not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')