with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix all ExternalUnknownState usages - replace inner imports and fix fields
content = content.replace(
    '''            # Create external unknown state (unresolved operation)
            from app.models.canonical_reliability import ExternalUnknownState
            unk1 = ExternalUnknownState(
                organization_id=org.id,
                canonical_operation_id=cop1.id,
                external_system="github",
                external_operation_id="ext-op-123",
                state="pending_verification",
                last_known_state="executing",
                uncertainty_reason="Network timeout during external API call",
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )''',
    '''            # Create external unknown state (unresolved operation)
            unk1 = ExternalUnknownState(
                organization_id=org.id,
                operation_id=cop1.id,
                external_system="github",
                external_operation_id="ext-op-123",
                external_operation_type="api_call",
                request_fingerprint=f"req-{uuid.uuid4().hex[:16]}",
                state="unknown",
                actor_id=admin_user.id,
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )'''
)

# Fix second occurrence
content = content.replace(
    '''            # Create external unknown state for decision linking
            from app.models.canonical_reliability import ExternalUnknownState
            unk1 = ExternalUnknownState(
                organization_id=org.id,
                canonical_operation_id=cop1.id,
                external_system="stripe",
                external_operation_id="payment-456",
                state="pending_verification",
                last_known_state="processing",
                uncertainty_reason="Payment gateway timeout",
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )''',
    '''            # Create external unknown state for decision linking
            unk1 = ExternalUnknownState(
                organization_id=org.id,
                operation_id=cop1.id,
                external_system="stripe",
                external_operation_id="payment-456",
                external_operation_type="payment",
                request_fingerprint=f"req-{uuid.uuid4().hex[:16]}",
                state="unknown",
                actor_id=admin_user.id,
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )'''
)

# Fix third occurrence
content = content.replace(
    '''            unk1 = ExternalUnknownState(
                organization_id=org.id,
                canonical_operation_id=cop1.id,
                external_system="aws",
                external_operation_id="lambda-789",
                state="pending_verification",
                last_known_state="executing",
                uncertainty_reason="Lambda timeout",
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )''',
    '''            unk1 = ExternalUnknownState(
                organization_id=org.id,
                operation_id=cop1.id,
                external_system="aws",
                external_operation_id="lambda-789",
                external_operation_type="lambda",
                request_fingerprint=f"req-{uuid.uuid4().hex[:16]}",
                state="unknown",
                actor_id=admin_user.id,
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )'''
)

# Fix fourth occurrence
content = content.replace(
    '''            unk2 = ExternalUnknownState(
                organization_id=org.id,
                canonical_operation_id=cop2.id,
                external_system="github",
                external_operation_id="ext-op-999",
                state="pending_verification",
                last_known_state="executing",
                uncertainty_reason="GitHub Actions timeout",
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )''',
    '''            unk2 = ExternalUnknownState(
                organization_id=org.id,
                operation_id=cop2.id,
                external_system="github",
                external_operation_id="ext-op-999",
                external_operation_type="github_actions",
                request_fingerprint=f"req-{uuid.uuid4().hex[:16]}",
                state="unknown",
                actor_id=admin_user.id,
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )'''
)

# Fix fifth occurrence
content = content.replace(
    '''            unk1 = ExternalUnknownState(
                organization_id=org.id,
                canonical_operation_id=cop1.id,
                external_system="aws",
                external_operation_id="lambda-111",
                state="pending_verification",
                last_known_state="executing",
                uncertainty_reason="Lambda timeout",
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )''',
    '''            unk1 = ExternalUnknownState(
                organization_id=org.id,
                operation_id=cop1.id,
                external_system="aws",
                external_operation_id="lambda-111",
                external_operation_type="lambda",
                request_fingerprint=f"req-{uuid.uuid4().hex[:16]}",
                state="unknown",
                actor_id=admin_user.id,
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )'''
)

# Fix sixth occurrence
content = content.replace(
    '''            unk1 = ExternalUnknownState(
                organization_id=org.id,
                canonical_operation_id=cop1.id,
                external_system="postgresql",
                external_operation_id="migration-001",
                state="unknown",
                fingerprint=f"unk-{uuid.uuid4().hex[:16]}"
            )''',
    '''            unk1 = ExternalUnknownState(
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
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed all ExternalUnknownState usages')