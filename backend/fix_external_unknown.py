with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ExternalUnknownState - different fields
old_unk = '''            unk1 = ExternalUnknownState(
                organization_id=org.id,
                canonical_operation_id=cop1.id,
                external_system="postgresql",
                external_operation_id="migration-001",
                state="unknown",
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )'''

new_unk = '''            unk1 = ExternalUnknownState(
                organization_id=org.id,
                operation_id=cop1.id,
                external_system="postgresql",
                external_operation_id="migration-001",
                external_operation_type="database_migration",
                request_fingerprint=f"req-{uuid.uuid4().hex[:16]}",
                state="unknown",
                actor_id=admin_user.id,
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )'''

content = content.replace(old_unk, new_unk)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed ExternalUnknownState fields')