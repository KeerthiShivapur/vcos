with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix WorkerLease
old_wl2 = '''            wl2 = WorkerLease(
                organization_id=org.id,
                worker_id=f"worker-{uuid.uuid4().hex[:8]}",
                lease_type="sync_worker",
                resource_type="connector_instance",
                resource_id=ci_github.id,
                expires_at=utcnow() + timedelta(minutes=30),
                fingerprint=f"wl-{uuid.uuid4().hex[:16]}"
            )'''

new_wl2 = '''            wl2 = WorkerLease(
                organization_id=org.id,
                worker_id="worker-" + uuid.uuid4().hex[:8],
                worker_type="sync_worker",
                operation_id=cop1.id,
                expires_at=utcnow() + timedelta(minutes=30)
            )'''

content = content.replace(old_wl2, new_wl2)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed WorkerLease')