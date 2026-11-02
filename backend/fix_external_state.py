with open('app/services/external_operation_service.py', 'r') as f:
    content = f.read()

# Fix _mark_unknown to use string literal instead of ExternalState.UNKNOWN
old = '''        # Create ExternalUnknownState record for reconciliation
        from app.models.canonical_reliability import ExternalUnknownState
        unknown = ExternalUnknownState(
            organization_id=operation.organization_id,
            source_operation_id=operation.id,
            external_system="connector",
            operation_type=operation.operation_type,
            target_external_id=operation.target_external_id,
            payload=operation.payload,
            reason=reason,
            state=ExternalState.UNKNOWN,
        )'''

new = '''        # Create ExternalUnknownState record for reconciliation
        from app.models.canonical_reliability import ExternalUnknownState
        unknown = ExternalUnknownState(
            organization_id=operation.organization_id,
            source_operation_id=operation.id,
            external_system="connector",
            operation_type=operation.operation_type,
            target_external_id=operation.target_external_id,
            payload=operation.payload,
            reason=reason,
            state="unknown",
        )'''

content = content.replace(old, new)

with open('app/services/external_operation_service.py', 'w') as f:
    f.write(content)
print('Fixed')