with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ConnectorInstance - remove fingerprint
content = content.replace(
    '''            ci_github = CI(
                organization_id=org.id,
                connector_id=conn_github.id,
                name="GitHub Production",
                config={"organization": "acme-corp"},
                credentials={"pat": "mock_pat_token"},
                state="connected",
                auth_type="pat",
                connected_at=utcnow(),
                fingerprint="ci-" + uuid.uuid4().hex[:16]
            )''',
    '''            ci_github = CI(
                organization_id=org.id,
                connector_id=conn_github.id,
                name="GitHub Production",
                config={"organization": "acme-corp"},
                credentials={"pat": "mock_pat_token"},
                state="connected",
                auth_type="pat",
                connected_at=utcnow()
            )'''
)

# Also fix Slack connector instance
content = content.replace(
    '''            ci_slack = CI(
                organization_id=org.id,
                connector_id=conn_slack.id,
                name="Slack Workspace",
                config={"workspace": "acme-corp"},
                credentials={"bot_token": "mock_bot_token"},
                state="connected",
                auth_type="bot",
                connected_at=utcnow(),
                fingerprint="ci-" + uuid.uuid4().hex[:16]
            )''',
    '''            ci_slack = CI(
                organization_id=org.id,
                connector_id=conn_slack.id,
                name="Slack Workspace",
                config={"workspace": "acme-corp"},
                credentials={"bot_token": "mock_bot_token"},
                state="connected",
                auth_type="bot",
                connected_at=utcnow()
            )'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed fingerprint from ConnectorInstance')