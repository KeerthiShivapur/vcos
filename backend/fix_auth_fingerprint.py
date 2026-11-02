import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add fingerprint to authorization creation
old_auth = '''        authorization = CompanyAuthorization(
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

new_auth = '''        authorization = CompanyAuthorization(
            organization_id=org.id,
            authorization_type="budget",
            title="Budget for Platform Modernization",
            rationale="Approve budget for platform modernization project",
            state="approved",
            scope_type="project",
            scope_id=project_platform.id,
            approved_by=access.employee_id,
            approved_at=utcnow(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )'''

if old_auth in content:
    content = content.replace(old_auth, new_auth)
    print('Fixed authorization fingerprint')
else:
    print('Block not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')