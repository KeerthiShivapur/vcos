with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix OperationAttempt - remove actor_id and actor_type, use worker_id instead
old_oa = '''            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="running",
                actor_id=admin_user.id,
                actor_type="human",
                started_at=utcnow(),
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )'''

new_oa = '''            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="running",
                worker_id=admin_user.id,
                worker_instance="admin",
                started_at=utcnow(),
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )'''

content = content.replace(old_oa, new_oa)

# Also fix second occurrence
old_oa2 = '''            oa2 = OperationAttempt(
                operation_id=cop2.id,
                organization_id=org.id,
                attempt_number=1,
                state="running",
                actor_id=admin_user.id,
                actor_type="human",
                started_at=utcnow(),
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )'''

new_oa2 = '''            oa2 = OperationAttempt(
                operation_id=cop2.id,
                organization_id=org.id,
                attempt_number=1,
                state="running",
                worker_id=admin_user.id,
                worker_instance="admin",
                started_at=utcnow(),
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )'''

content = content.replace(old_oa2, new_oa2)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed OperationAttempt fields')