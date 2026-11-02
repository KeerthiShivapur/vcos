with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix the Connector creation for GitHub - update the GitHub provider section
old = '''    connector = await db.execute(select(Connector).where(Connector.provider == provider, Connector.enabled == True))
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
        elif provider == "slack":'''

new = '''    connector = await db.execute(select(Connector).where(Connector.provider == provider, Connector.enabled == True))
    connector = connector.scalar_one_or_none()
    if not connector:
        if provider == "github":'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed part 1')