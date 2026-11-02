with open('test_real_integrations_provisioning_e2e.py', 'r') as f:
    content = f.read()

# Find the problematic section
start_idx = content.find('\n        # Use raw connection with explicit transaction for all org2 operations\n')
if start_idx == -1:
    start_idx = content.find('\n        # Use raw connection with explicit transaction for all org2 operations\n')

if start_idx != -1:
    print(f'Found start at index {start_idx}')
    
    # Find the end of the block - after the CI insert
    end_idx = content.find('\n            )', content.find('instance2_id = uuid.uuid4().hex'))
    if end_idx != -1:
        end_idx = content.find('\n            )', content.find('instance2_id = uuid.uuid4().hex')) + 1
        # Find the next line
        next_line = content.find('\n', end_idx)
        if next_line != -1:
            end_idx = next_line + 1
        else:
            end_idx = len(content)
        
        print(f'Found block from {start_idx} to {end_idx}')
        
        new_code = '''        # Use raw connection for all org2 operations (connection already has transaction from session)
        conn = await pg_db_session.connection()
        await conn.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": org2.id}
        )

        # Create connector for org2
        google_connector_result = await conn.execute(
            select(Connector.id).where(Connector.provider == "google")
        )
        connector_id = google_connector_result.scalar_one_or_none()
        if not connector_id:
            connector_id = uuid.uuid4().hex
            await conn.execute(
                Connector.__table__.insert().values(
                    id=connector_id,
                    kind="productivity",
                    provider="google",
                    display_name="Google Workspace",
                    description="Google Workspace integration",
                    inbound_capabilities=["read_people", "read_groups"],
                    outbound_capabilities=["write_messages"],
                    supported_entities=["person", "group", "channel"],
                    supported_events=[],
                    sync_modes=["incremental", "webhook"],
                    supports_webhooks=True,
                    supports_polling=True,
                    default_poll_interval_seconds=300,
                    auth_types=["oauth2"],
                    oauth_scopes=[],
                    required_config_fields=[],
                    optional_config_fields=[],
                    enabled=True,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
            )

        # Insert connector_instance in the same transaction
        instance2_id = uuid.uuid4().hex
        await conn.execute(
            CI.__table__.insert().values(
                id=instance2_id,
                organization_id=org2.id,
                connector_id=connector_id,
                name="Acme Second Google",
                config={},
                credentials={},
                state="disconnected",
                auth_type="oauth2",
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )'''
        
        content = content[:start_idx] + new_code + content[end_idx:]
        with open('test_real_integrations_provisioning_e2e.py', 'w') as f:
            f.write(content)
        print('File updated successfully')
    else:
        print('Could not find end of block')
else:
    print('Could not find start of block')

with open('test_real_integrations_provisioning_e2e.py', 'w') as f:
    f.write(content)