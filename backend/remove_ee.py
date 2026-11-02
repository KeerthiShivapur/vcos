with open('create_company_state.py', 'r') as f:
    content = f.read()

# Remove first ExternalEvent creation
old_ee1 = '''            # Create external event
            ee1 = ExternalEvent(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_event_id="evt-abc123",
                event_type="pull_request.opened",
                source_type="pull_request",
                payload={"action": "opened", "number": 42, "title": "Add new feature"},
                payload_hash="abc123",
                received_at=utcnow() - timedelta(hours=2),
                state="processed",
                processing_fingerprint="ee-" + uuid.uuid4().hex[:16]
            )
            db.add(ee1)'''

new_ee1 = '''            # ExternalEvent creation skipped - already exists'''

content = content.replace(old_ee1, new_ee1)

# Remove second ExternalEvent creation
old_ee2 = '''            # Create external event for Slack
            ee1 = ExternalEvent(
                organization_id=org.id,
                connector_instance_id=ci_slack.id,
                external_event_id="evt-def456",
                event_type="message",
                source_type="message",
                payload={"text": "Hello world", "channel": "C123", "user": "U123"},
                payload_hash="def456",
                received_at=utcnow() - timedelta(hours=1),
                state="processed",
                processing_fingerprint="ee-" + uuid.uuid4().hex[:16]
            )
            db.add(ee1)'''

new_ee2 = '''            # ExternalEvent creation skipped - already exists'''

content = content.replace(old_ee2, new_ee2)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed ExternalEvent creations')