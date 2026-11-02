import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the authorization mutation to include provenance
old_auth_mutate = '''        auth_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(authorization), db.flush(), authorization)[2],
        )'''

new_auth_mutate = '''        auth_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(authorization), db.flush(), authorization)[2],
            provenance={"decision_id": decision_id},
        )'''

if old_auth_mutate in content:
    content = content.replace(old_auth_mutate, new_auth_mutate)
    print('Fixed authorization provenance')
else:
    print('Block not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')