import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the commitment creation to include required provenance
old_commitment_fn = '''        async def create_commitment_fn(db):
            db.add(commitment)
            await db.flush()
            return commitment
        
        commitment_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_commitment_fn,
        )'''

new_commitment_fn = '''        async def create_commitment_fn(db):
            db.add(commitment)
            await db.flush()
            return commitment
        
        commitment_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_commitment_fn,
            provenance={"authorization_id": authorization_id, "source_company_decision_id": decision_id},
        )'''

if old_commitment_fn in content:
    content = content.replace(old_commitment_fn, new_commitment_fn)
    print('Fixed commitment mutation provenance')

# Also fix the second commitment creation
old_commitment_fn2 = '''        async def create_commitment_fn(db):
            db.add(new_commitment)
            await db.flush()
            return new_commitment
        
        new_com_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_commitment_fn,
        )'''

new_commitment_fn2 = '''        async def create_commitment_fn(db):
            db.add(new_commitment)
            await db.flush()
            return new_commitment
        
        new_com_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyCommitment",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_commitment_fn,
            provenance={"authorization_id": new_auth_result.entity.id, "source_company_decision_id": new_dec_result.entity.id},
        )'''

if old_commitment_fn2 in content:
    content = content.replace(old_commitment_fn2, new_commitment_fn2)
    print('Fixed second commitment mutation provenance')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed commitment provenance')