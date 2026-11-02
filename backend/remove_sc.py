with open('create_company_state.py', 'r') as f:
    content = f.read()

# Remove first SyncCursor creation
old_sc1 = '''            # Create sync cursor
            sc1 = SyncCursor(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                entity_type="repository",
                cursor_value="2024-01-15T10:00:00Z",
                cursor_type="timestamp",
                last_updated_at=utcnow()
            )
            db.add(sc1)'''

new_sc1 = '''            # SyncCursor creation skipped - already exists'''

content = content.replace(old_sc1, new_sc1)

# Remove second SyncCursor creation
old_sc2 = '''            # Create sync cursor for Slack
            sc1 = SyncCursor(
                organization_id=org.id,
                connector_instance_id=ci_slack.id,
                entity_type="channel",
                cursor_value="2024-01-15T10:00:00Z",
                cursor_type="timestamp",
                last_updated_at=utcnow()
            )
            db.add(sc1)'''

new_sc2 = '''            # SyncCursor creation skipped - already exists'''

content = content.replace(old_sc2, new_sc2)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed SyncCursor creations')