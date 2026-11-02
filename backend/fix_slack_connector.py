with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix Slack connector creation
old_slack = '''            # Create connector instance for Slack
            conn_slack = Connector(
                kind="communication",
                provider="slack",
                display_name="Slack",
                description="Slack integration for notifications",
                inbound_capabilities=["read_channels", "read_messages", "read_users"],
                outbound_capabilities=["send_messages", "update_messages", "delete_messages"],
                supported_entities=["channel", "message", "user", "thread"],
                supported_events=["message", "reaction_added", "channel_created"],
                sync_modes=["incremental", "webhook"],
                supports_webhooks=True,
                supports_polling=True,
                default_poll_interval_seconds=300,
                auth_types=["bot_token"],
                oauth_scopes=["channels:read", "channels:history", "chat:write", "users:read"],
                required_config_fields=["workspace_id", "bot_token"],
                optional_config_fields=["signing_secret"],
                enabled=True
            )
            db.add(conn_slack)
            await db.flush()
            
            ci_slack = CI(
                organization_id=org.id,
                connector_id=conn_slack.id,
                name="Slack Production",
                config={"workspace_id": "T123456"},
                credentials={"bot_token": "xoxb-mock-token"},
                state="connected",
                auth_type="bot_token",
                connected_at=utcnow(),
                fingerprint=f"ci-{uuid.uuid4().hex[:16]}"
            )
            db.add(ci_slack)
            await db.flush()'''

new_slack = '''            # Query existing Slack connector
            result = await db.execute(select(Connector).where(Connector.kind == "communication", Connector.provider == "slack"))
            conn_slack = result.scalars().first()
            if not conn_slack:
                conn_slack = Connector(
                    kind="communication",
                    provider="slack",
                    display_name="Slack",
                    description="Slack integration for notifications",
                    inbound_capabilities=["read_channels", "read_messages", "read_users"],
                    outbound_capabilities=["send_messages", "update_messages", "delete_messages"],
                    supported_entities=["channel", "message", "user", "thread"],
                    supported_events=["message", "reaction_added", "channel_created"],
                    sync_modes=["incremental", "webhook"],
                    supports_webhooks=True,
                    supports_polling=True,
                    default_poll_interval_seconds=300,
                    auth_types=["bot_token"],
                    oauth_scopes=["channels:read", "channels:history", "chat:write", "users:read"],
                    required_config_fields=["workspace_id", "bot_token"],
                    optional_config_fields=["signing_secret"],
                    enabled=True
                )
                db.add(conn_slack)
                await db.flush()
            
            result = await db.execute(select(CI).where(CI.organization_id == org.id, CI.connector_id == conn_slack.id))
            ci_slack = result.scalars().first()
            if not ci_slack:
                ci_slack = CI(
                    organization_id=org.id,
                    connector_id=conn_slack.id,
                    name="Slack Production",
                    config={"workspace_id": "T123456"},
                    credentials={"bot_token": "xoxb-mock-token"},
                    state="connected",
                    auth_type="bot_token",
                    connected_at=utcnow()
                )
                db.add(ci_slack)
                await db.flush()'''

content = content.replace(old_slack, new_slack)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed Slack connector creation')