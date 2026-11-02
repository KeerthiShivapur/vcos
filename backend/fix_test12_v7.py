with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix the indentation for test_12_revoked_authorization_blocks_operation
old = '''        org_id, admin_user, admin_emp, access = await _provision_company(pg_db_session, f"revoked-auth-{uuid.uuid4().hex[:8]}")
        
            instance = await _create_connector_instance(pg_db_session, org_id, "github")
        
        # Create authorization then revoke it (supersede)
        from app.models.execution_strategy import CompanyAuthorization
        auth = CompanyAuthorization('''

new = '''        org_id, admin_user, admin_emp, access = await _provision_company(pg_db_session, f"revoked-auth-{uuid.uuid4().hex[:8]}")
        
        instance = await _create_connector_instance(pg_db_session, org_id, "github")
        
        # Create authorization then revoke it (supersede)
        from app.models.execution_strategy import CompanyAuthorization
        auth = CompanyAuthorization('''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')