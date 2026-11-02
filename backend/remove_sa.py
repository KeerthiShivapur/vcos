with open('create_company_state.py', 'r') as f:
    content = f.read()

# Remove first SourceAuthority creation
old_sa1 = '''            # Create source authority
            sa1 = SourceAuthority(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                entity_type="repository",
                authority_level="primary",
                precedence=100,
                configured_by=admin_user.id
            )
            db.add(sa1)'''

new_sa1 = '''            # SourceAuthority creation skipped - already exists'''

content = content.replace(old_sa1, new_sa1)

# Remove second SourceAuthority creation
old_sa2 = '''            # Create source authority for Slack
            sa1 = SourceAuthority(
                organization_id=org.id,
                connector_instance_id=ci_slack.id,
                entity_type="channel",
                authority_level="primary",
                precedence=100,
                configured_by=admin_user.id
            )
            db.add(sa1)'''

new_sa2 = '''            # SourceAuthority creation skipped - already exists'''

content = content.replace(old_sa2, new_sa2)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed SourceAuthority creations')