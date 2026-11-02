with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix the indentation
old = '        instance = await _create_connector_instance(pg_db_session, org_id, "github")\n        \n        # Create authorization then revoke it (supersede)\n        from app.models.execution_strategy import CompanyAuthorization\n        auth = CompanyAuthorization('

new = '        instance = await _create_connector_instance(pg_db_session, org_id, "github")\n        \n        # Create authorization then revoke it (supersede)\n        from app.models.execution_strategy import CompanyAuthorization\n        auth = CompanyAuthorization('

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')