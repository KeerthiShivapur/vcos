with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix SyncRun - remove invalid fields
old_sr = '''            sr1 = SyncRun(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                sync_mode="incremental",
                state="completed",
                started_at=utcnow() - timedelta(hours=1),
                completed_at=utcnow(),
                entities_processed=150,
                entities_created=10,
                entities_updated=5,
                entities_deleted=0,
                conflicts_detected=0,
                conflicts_resolved=0,
                fingerprint=f"sr-{uuid.uuid4().hex[:16]}"
            )'''

new_sr = '''            sr1 = SyncRun(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                sync_mode="incremental",
                state="completed",
                started_at=utcnow() - timedelta(hours=1),
                completed_at=utcnow(),
                entities_processed=150,
                entities_created=10,
                entities_updated=5,
                entities_deleted=0,
                conflicts_detected=0
            )'''

content = content.replace(old_sr, new_sr)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed SyncRun fields')