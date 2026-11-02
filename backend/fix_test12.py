with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix test_12_revoked_authorization_blocks_operation - use 'superseded' instead of 'revoked'
old = '''        instance = await _create_connector_instance(pg_db_session, org_id, "google")
        
        # Create authorization then revoke
        auth = CompanyAuthorization(
            organization_id=org_id,
            title="Test Authorization",
            state="revoked",
        )'''

new = '''        instance = await _create_connector_instance(pg_db_session, org_id, "google")
        
        # Create authorization then revoke (supersede)
        auth = CompanyAuthorization(
            organization_id=org_id,
            title="Test Authorization",
            state="superseded",
        )'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')