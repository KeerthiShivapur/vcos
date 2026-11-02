with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Add Slack provider support
old = '''        elif provider == "jira":
            connector = Connector(
                kind="work_management",
                provider=provider,
                display_name=provider.title(),
                description=f"{provider.title()} integration",
                inbound_capabilities=["read_issues", "read_projects", "read_users"],
                outbound_capabilities=["write_issues", "transition_issues"],
                supported_entities=["issue", "project", "user", "sprint"],
                supported_events=["issue_created", "issue_updated", "issue_deleted"],
                sync_modes=["incremental", "webhook"],'''

new = '''        elif provider == "slack":
            connector = Connector(
                kind="communication",
                provider=provider,
                display_name=provider.title(),
                description=f"{provider.title()} integration",
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
                enabled=True,
            )
        elif provider == "jira":'''

content = content.replace(
    '''        elif provider == "jira":
            connector = Connector(
                kind="work_management",
                provider=provider,
                display_name=provider.title(),
                description=f"{provider.title()} integration",
                inbound_capabilities=["read_issues", "read_projects", "read_users"],
                outbound_capabilities=["write_issues", "transition_issues"],
                supported_entities=["issue", "project", "user", "sprint"],
                supported_events=["issue_created", "issue_updated", "issue_deleted"],
                sync_modes=["incremental", "webhook"],''',
    '''        elif provider == "slack":
            connector = Connector(
                kind="communication",
                provider=provider,
                display_name=provider.title(),
                description=f"{provider.title()} integration",
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
                enabled=True,
            )
        elif provider == "jira":''')

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')