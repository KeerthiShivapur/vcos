import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Swap the order: create authorization first, then commitment
# Find the section from commitment creation to after authorization creation
old_section = '''        # Create commitment through canonical mutation
        commitment = CompanyCommitment(
            organization_id=org.id,
            commitment_type="deliverable",
            title="Deliver API v2 by Q2",
            rationale="Complete API v2 design and implementation",
            state="active",
            scope_type="project",
            scope_id=project_platform.id,
            objective_id=None,
            start_date=utcnow().date(),
            target_date=(utcnow() + timedelta(days=90)).date(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_commitment_fn(db):
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
        )
        assert commitment_result.success, f"Commitment creation failed: {commitment_result.error}"
        commitment_id = commitment_result.entity.id
        
        # Create authorization through canonical mutation
        authorization = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="budget",
            title="Budget for Platform Modernization",
            rationale="Approve budget for platform modernization project",
            state="approved",
            scope_type="project",
            scope_id=project_platform.id,
            approver_label=access.employee_id,
            approved_at=utcnow(),
        )
        
        auth_result = await canonical_mutation_boundary.mutate(
            db_session,
            access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            entity=authorization,
        )
        assert auth_result.success, f"Authorization creation failed: {auth_result.error}"
        authorization_id = auth_result.entity.id'''

new_section = '''        # Create authorization through canonical mutation FIRST (needed for commitment provenance)
        authorization = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="budget",
            title="Budget for Platform Modernization",
            rationale="Approve budget for platform modernization project",
            state="approved",
            scope_type="project",
            scope_id=project_platform.id,
            approver_label=access.employee_id,
            approved_at=utcnow(),
        )
        
        auth_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyAuthorization",
            mutation_type=MutationType.CREATE,
            mutation_fn=lambda db: (db.add(authorization), db.flush(), authorization)[2],
        )
        assert auth_result.success, f"Authorization creation failed: {auth_result.error}"
        authorization_id = auth_result.entity.id
        
        # Create commitment through canonical mutation
        commitment = CompanyCommitment(
            organization_id=org.id,
            commitment_type="deliverable",
            title="Deliver API v2 by Q2",
            rationale="Complete API v2 design and implementation",
            state="active",
            scope_type="project",
            scope_id=project_platform.id,
            objective_id=None,
            start_date=utcnow().date(),
            target_date=(utcnow() + timedelta(days=90)).date(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )
        
        async def create_commitment_fn(db):
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
        )
        assert commitment_result.success, f"Commitment creation failed: {commitment_result.error}"
        commitment_id = commitment_result.entity.id'''

if old_section in content:
    content = content.replace(old_section, new_section)
    print('Reordered authorization and commitment creation')
else:
    print('Section not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')