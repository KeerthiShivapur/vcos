with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix OperationAttempt - actor_id -> worker_id, actor_type -> worker_instance
old_oa = '''            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                actor_id="system",
                actor_type="system",
                started_at=utcnow() - timedelta(minutes=5),
                completed_at=utcnow(),
                outcome="success",
                result_json={"repos_synced": 50},
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )'''

new_oa = '''            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                worker_id="system",
                worker_instance="system",
                started_at=utcnow() - timedelta(minutes=5),
                completed_at=utcnow(),
                outcome="success",
                result_json={"repos_synced": 50},
                fingerprint="oa-" + uuid.uuid4().hex[:16]
            )'''

content = content.replace(old_oa, new_oa)

# Fix third occurrence
old_oa3 = '''            oa1 = OperationAttempt(
                operation_id=cop2.id,
                organization_id=org.id,
                attempt_number=1,
                state="running",
                actor_id=admin_user.id,
                actor_type="human",
                started_at=utcnow(),
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )'''

new_oa3 = '''            oa1 = OperationAttempt(
                operation_id=cop2.id,
                organization_id=org.id,
                attempt_number=1,
                state="running",
                worker_id=admin_user.id,
                worker_instance="admin",
                started_at=utcnow(),
                fingerprint="oa-" + uuid.uuid4().hex[:16]
            )'''

content = content.replace(old_oa3, new_oa3)

# Fix fourth occurrence
old_oa4 = '''            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                actor_id="system",
                actor_type="system",
                started_at=utcnow() - timedelta(minutes=3),
                completed_at=utcnow(),
                outcome="success",
                result_json={"external_synced": 100},
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )'''

new_oa4 = '''            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                worker_id="system",
                worker_instance="system",
                started_at=utcnow() - timedelta(minutes=3),
                completed_at=utcnow(),
                outcome="success",
                result_json={"external_synced": 100},
                fingerprint="oa-" + uuid.uuid4().hex[:16]
            )'''

content = content.replace(old_oa4, new_oa4)

# Fix fifth occurrence
old_oa5 = '''            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                actor_id="system",
                actor_type="system",
                started_at=utcnow() - timedelta(minutes=2),
                completed_at=utcnow(),
                outcome="success",
                result_json={"repos_synced": 50},
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )'''

new_oa5 = '''            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                worker_id="system",
                worker_instance="system",
                started_at=utcnow() - timedelta(minutes=2),
                completed_at=utcnow(),
                outcome="success",
                result_json={"repos_synced": 50},
                fingerprint="oa-" + uuid.uuid4().hex[:16]
            )'''

content = content.replace(old_oa5, new_oa5)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed OperationAttempt fields')