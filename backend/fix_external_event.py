with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ExternalEvent
old_ee = '''            ee1 = ExternalEvent(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_event_id=f"evt-{uuid.uuid4().hex[:8]}",
                event_type="pull_request.opened",
                event_subtype="pull_request",
                payload={"action": "opened", "number": 42, "title": "Add new feature"},
                payload_hash="abc123",
                received_at=utcnow() - timedelta(hours=2),
                state="processed",
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

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed ExternalEvent fields')