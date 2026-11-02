with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix _create_connector_instance to use correct capabilities for each provider
old = '''    connector = await db.execute(select(Connector).where(Connector.provider == provider, Connector.enabled == True))
    connector = connector.scalar_one_or_none()
    if not connector:
        connector = Connector(
            kind="productivity" if provider in ["google", "microsoft"] else
                 "communication" if provider == "slack" else
                 "code" if provider == "github" else
                 "work_management",
            provider=provider,
            display_name=provider.title(),
            description=f"{provider.title()} integration",
            inbound_capabilities=["read_people", "read_groups"],
            outbound_capabilities=["write_messages"],
            supported_entities=["person", "group"],
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
        )
        db.add(connector)
        await db.flush()'''

new = '''    connector = await db.execute(select(Connector).where(Connector.provider == provider, Connector.enabled == True))
    connector = connector.scalar_one_or_none()
    if not connector:
        if provider == "github":
            connector = Connector(
                kind="code",
                provider=provider,
                display_name=provider.title(),
                description=f"{provider.title()} integration",
                inbound_capabilities=["read_repos", "read_issues", "read_pull_requests", "read_commits"],
                outbound_capabilities=["read"],
                supported_entities=["repository", "issue", "pull_request", "commit", "person"],
                supported_events=["push", "pull_request", "issues"],
                sync_modes=["incremental", "webhook"],
                supports_webhooks=True,
                supports_polling=True,
                default_poll_interval_seconds=300,
                auth_types=["pat"],
                oauth_scopes=["repo", "read:org", "read:user"],
                required_config_fields=["organization"],
                optional_config_fields=[],
                enabled=True,
            )
        elif provider == "slack":
            connector = Connector(
                kind="communication",
                provider=provider,
                display_name=provider.title(),
                description=f"{provider.title()} integration",
                inbound_capabilities=["read_people", "read_channels"],
                outbound_capabilities=["write_messages"],
                supported_entities=["person", "channel", "message"],
                supported_events=["message", "reaction"],
                sync_modes=["incremental", "webhook"],
                supports_webhooks=True,
                supports_polling=True,
                default_poll_interval_seconds=300,
                auth_types=["bot_token"],
                oauth_scopes=["channels:read", "groups:read", "users:read", "chat:write"],
                required_config_fields=["workspace"],
                optional_config_fields=[],
                enabled=True,
            )
        elif provider in ["google", "microsoft"]:
            connector = Connector(
                kind="productivity",
                provider=provider,
                display_name=provider.title(),
                description=f"{provider.title()} integration",
                inbound_capabilities=["read_people", "read_groups", "read_calendar", "read_drive"],
                outbound_capabilities=["write_calendar", "write_drive"],
                supported_entities=["person", "group", "event", "file"],
                supported_events=["calendar", "drive"],
                sync_modes=["incremental", "webhook"],
                supports_webhooks=True,
                supports_polling=True,
                default_poll_interval_seconds=300,
                auth_types=["oauth2"],
                oauth_scopes=["openid", "email", "profile", "https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/drive"],
                required_config_fields=["domain"],
                optional_config_fields=[],
                enabled=True,
            )
        elif provider == "jira":
            connector = Connector(
                kind="work_management",
                provider=provider,
                display_name=provider.title(),
                description=f"{provider.title()} integration",
                inbound_capabilities=["read_issues", "read_projects", "read_users"],
                outbound_capabilities=["write_issues", "transition_issues"],
                supported_entities=["issue", "project", "user", "sprint"],
                supported_events=["issue_created", "issue_updated", "issue_deleted"],
                sync_modes=["incremental", "webhook"],
                supports_webhooks=True,
                supports_polling=True,
                default_poll_interval_seconds=300,
                auth_types=["api_token", "oauth2"],
                oauth_scopes=["read:jira-work", "write:jira-work"],
                required_config_fields=["cloud_id"],
                optional_config_fields=[],
                enabled=True,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        db.add(connector)
        await db.flush()'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')