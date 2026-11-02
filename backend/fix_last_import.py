with open('create_company_state.py', 'r') as f:
    content = f.read()

# Remove inner import at line 1093
content = content.replace(
    '''            # Create external unknown state
            from app.models.canonical_reliability import ExternalUnknownState
            unk1 = ExternalUnknownState(
                organization_id=org.id,
                canonical_operation_id="cop-123",
                external_system="github",
                external_operation_id="ext-op-123",
                state="pending_verification",
                last_known_state="executing",
                uncertainty_reason="Network timeout during external API call",
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )''',
    '''            # Create external unknown state
            unk1 = ExternalUnknownState(
                organization_id=org.id,
                operation_id="cop-123",
                external_system="github",
                external_operation_id="ext-op-123",
                external_operation_type="api_call",
                request_fingerprint=f"req-{uuid.uuid4().hex[:16]}",
                state="unknown",
                actor_id=admin_user.id,
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed inner import at line 1093')