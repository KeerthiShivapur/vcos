with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix _create_connector_instance to update existing Connector with correct capabilities for GitHub
old = '''_create_connector_instance(db: AsyncSession, org_id: str, provider: str, name: str = None) -> CI:
    """Create a connector instance for a provider."""
    connector = await db.execute(select(Connector).where(Connector.provider == provider, Connector.enabled == True))
    connector = connector.scalar_one_or_none()
    if not connector:
        if provider == "github":
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
            )'''

new = '''_create_connector_instance(db: AsyncSession, org_id: str, provider: str, name: str = None) -> CI:
    """Create a connector instance for a provider."""
    connector = await db.execute(select(Connector).where(Connector.provider == provider, Connector.enabled == True))
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
            )'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')