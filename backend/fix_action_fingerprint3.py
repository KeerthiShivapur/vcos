import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add fingerprint to action creation
old_action = '''        action = CompanyAction(
            organization_id=org.id,
            action_type="execute",
            title="Implement API Gateway",
            why="Implement API gateway for microservices",
            state="in_progress",
            assignee_id=access.employee_id,
            source_company_decision_id=decision_id,
            started_at=utcnow(),
        )'''

new_action = '''        action = CompanyAction(
            organization_id=org.id,
            action_type="execute",
            title="Implement API Gateway",
            why="Implement API gateway for microservices",
            state="in_progress",
            assignee_id=access.employee_id,
            source_company_decision_id=decision_id,
            started_at=utcnow(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )'''

if old_action in content:
    content = content.replace(old_action, new_action)
    print('Fixed action fingerprint')
else:
    print('Block not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')