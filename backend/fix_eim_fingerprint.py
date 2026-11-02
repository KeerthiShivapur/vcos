with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ExternalIdentityMapping - remove fingerprint
content = content.replace(
    '''            eim1 = ExternalIdentityMapping(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_id="github_user_123",
                external_email="john.doe@github.com",
                external_display_name="John Doe",
                vcos_entity_type="employee",
                vcos_entity_id=emp1.id,
                mapping_state="mapped",
                fingerprint=f"eim-{uuid.uuid4().hex[:16]}"
            )''',
    '''            eim1 = ExternalIdentityMapping(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_id="github_user_123",
                external_email="john.doe@github.com",
                external_display_name="John Doe",
                vcos_entity_type="employee",
                vcos_entity_id=emp1.id,
                mapping_state="mapped"
            )'''
)

# Fix second occurrence
content = content.replace(
    '''            eim2 = ExternalIdentityMapping(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_id="github_user_456",
                external_email="jane.smith@github.com",
                external_display_name="Jane Smith",
                vcos_entity_type="employee",
                vcos_entity_id=emp2.id,
                mapping_state="mapped",
                fingerprint=f"eim-{uuid.uuid4().hex[:16]}"
            )''',
    '''            eim2 = ExternalIdentityMapping(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_id="github_user_456",
                external_email="jane.smith@github.com",
                external_display_name="Jane Smith",
                vcos_entity_type="employee",
                vcos_entity_id=emp2.id,
                mapping_state="mapped"
            )'''
)

# Fix third occurrence
content = content.replace(
    '''            eim3 = ExternalIdentityMapping(
                organization_id=org.id,
                connector_instance_id=ci_slack.id,
                external_id="slack_user_789",
                external_email="bob.wilson@slack.com",
                external_display_name="Bob Wilson",
                vcos_entity_type="employee",
                vcos_entity_id=emp3.id,
                mapping_state="mapped",
                fingerprint=f"eim-{uuid.uuid4().hex[:16]}"
            )''',
    '''            eim3 = ExternalIdentityMapping(
                organization_id=org.id,
                connector_instance_id=ci_slack.id,
                external_id="slack_user_789",
                external_email="bob.wilson@slack.com",
                external_display_name="Bob Wilson",
                vcos_entity_type="employee",
                vcos_entity_id=emp3.id,
                mapping_state="mapped"
            )'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed fingerprint from ExternalIdentityMapping')