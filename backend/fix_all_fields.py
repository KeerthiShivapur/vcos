import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Comprehensive field name fixes based on actual models

replacements = [
    # CompanyDecision fixes
    ('decision_date=utcnow(),', 'approved_at=utcnow(),'),
    ('decided_by=', 'approver_label='),
    ('description=', 'rationale='),
    
    # CompanyCommitment fixes
    ('due_date=', 'target_date='),
    ('start_date=', 'start_date='),  # this is valid
    
    # CompanyAuthorization fixes - these should be OK
    # CompanyAction fixes
    # ('due_at=' is valid, 'due_date=' would be invalid)
    
    # Fix the Post-Restore Strategic Decision
    ('decision_date=utcnow(),', 'approved_at=utcnow(),'),
]

# Apply simple string replacements
for old, new in replacements:
    content = content.replace(old, new)

# Now fix specific blocks that need more complex changes
# Fix CompanyCommitment creation in main test
old_commitment = '''        # Create commitment through canonical mutation
        commitment = CompanyCommitment(
            organization_id=org.id,
            commitment_type="deliverable",
            title="Deliver API v2 by Q2",
            description="Complete API v2 design and implementation",
            state="active",
            scope_type="project",
            scope_id=project_platform.id,
            objective_id=None,
            start_date=utcnow().date(),
            due_date=(utcnow() + timedelta(days=90)).date(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )'''

new_commitment = '''        # Create commitment through canonical mutation
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
        )'''

if old_commitment in content:
    content = content.replace(old_commitment, new_commitment)
    print('Fixed CompanyCommitment creation')

# Fix CompanyAuthorization creation
old_auth = '''        # Create authorization through canonical mutation
        authorization = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="budget",
            title="Budget for Platform Modernization",
            description="Approve budget for platform modernization project",
            state="approved",
            scope_type="project",
            scope_id=project_platform.id,
            decided_by=access.employee_id,
            approved_at=utcnow(),
        )'''

new_auth = '''        # Create authorization through canonical mutation
        authorization = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="budget",
            title="Budget for Platform Modernization",
            rationale="Approve budget for platform modernization project",
            state="approved",
            scope_type="project",
            scope_id=project_platform.id,
            approved_by=access.employee_id,
            approved_at=utcnow(),
        )'''

if old_auth in content:
    content = content.replace(old_auth, new_auth)
    print('Fixed CompanyAuthorization creation')

# Fix CompanyAction creation
old_action = '''        # Create action through canonical mutation (with provenance)
        action = CompanyAction(
            organization_id=org.id,
            action_type="execute",
            title="Implement API Gateway",
            description="Implement API gateway for microservices",
            state="in_progress",
            assignee_id=access.employee_id,
            source_company_decision_id=decision_id,
            source_authorization_id=authorization_id,
            started_at=utcnow(),
        )'''

new_action = '''        # Create action through canonical mutation (with provenance)
        action = CompanyAction(
            organization_id=org.id,
            action_type="execute",
            title="Implement API Gateway",
            description="Implement API gateway for microservices",
            state="in_progress",
            assignee_id=access.employee_id,
            source_company_decision_id=decision_id,
            source_authorization_id=authorization_id,
            started_at=utcnow(),
        )'''

if old_action in content:
    content = content.replace(old_action, new_action)
    print('Fixed CompanyAction creation (already correct)')

# Fix the second CompanyAction (Post-Restore Action)
old_action2 = '''        # Create new action post-restore
        new_action = CompanyAction(
            organization_id=org.id,
            action_type="execute",
            title="Post-Restore Action",
            description="New action after disaster recovery",
            state="ready",
            assignee_id=access.employee_id,
            source_company_decision_id=new_dec_result.entity.id,
            source_authorization_id=new_auth_result.entity.id,
        )'''

new_action2 = '''        # Create new action post-restore
        new_action = CompanyAction(
            organization_id=org.id,
            action_type="execute",
            title="Post-Restore Action",
            description="New action after disaster recovery",
            state="ready",
            assignee_id=access.employee_id,
            source_company_decision_id=new_dec_result.entity.id,
            source_authorization_id=new_auth_result.entity.id,
        )'''

if old_action2 in content:
    content = content.replace(old_action2, new_action2)
    print('Fixed second CompanyAction creation (already correct)')

# Fix the second CompanyAuthorization (Post-Restore Budget)
old_auth2 = '''        # Create new authorization post-restore
        new_auth = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="budget",
            title="Post-Restore Budget",
            description="New budget after disaster recovery",
            state="proposed",
            scope_type="company",
            scope_id=org.id,
        )'''

new_auth2 = '''        # Create new authorization post-restore
        new_auth = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="budget",
            title="Post-Restore Budget",
            rationale="New budget after disaster recovery",
            state="proposed",
            scope_type="company",
            scope_id=org.id,
        )'''

if old_auth2 in content:
    content = content.replace(old_auth2, new_auth2)
    print('Fixed second CompanyAuthorization creation')

# Fix the second CompanyCommitment (Post-Restore Deliverable)
old_commitment2 = '''        # Create new commitment post-restore
        new_commitment = CompanyCommitment(
            organization_id=org.id,
            commitment_type="deliverable",
            title="Post-Restore Deliverable",
            description="New commitment after disaster recovery",
            state="active",
            scope_type="company",
            scope_id=org.id,
            start_date=utcnow().date(),
            due_date=(utcnow() + timedelta(days=30)).date(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )'''

new_commitment2 = '''        # Create new commitment post-restore
        new_commitment = CompanyCommitment(
            organization_id=org.id,
            commitment_type="deliverable",
            title="Post-Restore Deliverable",
            rationale="New commitment after disaster recovery",
            state="active",
            scope_type="company",
            scope_id=org.id,
            start_date=utcnow().date(),
            target_date=(utcnow() + timedelta(days=30)).date(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )'''

if old_commitment2 in content:
    content = content.replace(old_commitment2, new_commitment2)
    print('Fixed second CompanyCommitment creation')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('All field fixes applied')