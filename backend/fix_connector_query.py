with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix connector creation - query existing first
old_conn = '''            # Create connector and connector instance
            conn_github = Connector(
                kind="code",
                provider="github",
                display_name="GitHub",
                description="GitHub integration for repositories and issues",
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
                enabled=True
            )
            db.add(conn_github)
            await db.flush()
            
            ci_github = CI(
                organization_id=org.id,
                connector_id=conn_github.id,
                name="GitHub Production",
                config={"organization": "acme-corp"},
                credentials={"pat": "mock_pat_token"},
                state="connected",
                auth_type="pat",
                connected_at=utcnow(),
                fingerprint=f"ci-{uuid.uuid4().hex[:16]}"
            )
            db.add(ci_github)
            await db.flush()'''

new_conn = '''            # Query existing connectors
            result = await db.execute(select(Connector).where(Connector.kind == "code", Connector.provider == "github"))
            conn_github = result.scalars().first()
            if not conn_github:
                conn_github = Connector(
                    kind="code",
                    provider="github",
                    display_name="GitHub",
                    description="GitHub integration for repositories and issues",
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
                    enabled=True
                )
                db.add(conn_github)
                await db.flush()
            
            result = await db.execute(select(CI).where(CI.organization_id == org.id, CI.connector_id == conn_github.id))
            ci_github = result.scalars().first()
            if not ci_github:
                ci_github = CI(
                    organization_id=org.id,
                    connector_id=conn_github.id,
                    name="GitHub Production",
                    config={"organization": "acme-corp"},
                    credentials={"pat": "mock_pat_token"},
                    state="connected",
                    auth_type="pat",
                    connected_at=utcnow(),
                    fingerprint="ci-" + uuid.uuid4().hex[:16]
                )
                db.add(ci_github)
                await db.flush()'''

content = content.replace(old_conn, new_conn)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed connector creation to query existing')