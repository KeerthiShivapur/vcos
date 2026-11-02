with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ExternalEvent - replace all occurrences
old_ee = '''            ee1 = ExternalEvent(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_event_id=f"evt-{uuid.uuid4().hex[:8]}",
                event_type="pull_request.opened",
                event_subtype="pull_request",
                payload={"action": "opened", "number": 42, "title": "Add new feature"},
                payload_hash="abc123",
                received_at=utcnow() - timedelta(hours=2),
                processed_at=utcnow() - timedelta(hours=1, minutes=58),
                processing_state="completed",
                fingerprint=f"ee-{uuid.uuid4().hex[:16]}"
            )'''

new_ee = '''            ee1 = ExternalEvent(
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
            )'''

content = content.replace(old_ee, new_ee)

# Fix second occurrence
old_ee2 = '''            ee1 = ExternalEvent(
                organization_id=org.id,
                connector_instance_id=ci_slack.id,
                external_event_id=f"evt-{uuid.uuid4().hex[:8]}",
                event_type="message",
                event_subtype="message",
                payload={"text": "Hello world", "channel": "C123", "user": "U123"},
                payload_hash="def456",
                received_at=utcnow() - timedelta(hours=1),
                processed_at=utcnow() - timedelta(minutes=59),
                processing_state="completed",
                fingerprint=f"ee-{uuid.uuid4().hex[:16]}"
            )'''

new_ee2 = '''            ee1 = ExternalEvent(
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
            )'''

content = content.replace(old_ee2, new_ee2)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed ExternalEvent fields')