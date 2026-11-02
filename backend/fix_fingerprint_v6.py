with open('app/services/external_operation_service.py', 'r') as f:
    content = f.read()

# Fix _mark_unknown to set both request_fingerprint and fingerprint
old = '''        unknown = ExternalUnknownState(
            organization_id=operation.organization_id,
            operation_id=operation.id,
            external_system="connector",
            external_operation_id=operation.external_operation_id or f"local-{operation.id}",
            external_operation_type=operation.operation_type,
            request_payload_json=operation.payload,
            request_fingerprint=fingerprint,
            fingerprint=fingerprint,
            state="unknown",
        )'''

new = '''        unknown = ExternalUnknownState(
            organization_id=operation.organization_id,
            operation_id=operation.id,
            external_system="connector",
            external_operation_id=operation.external_operation_id or f"local-{operation.id}",
            external_operation_type=operation.operation_type,
            request_payload_json=operation.payload,
            request_fingerprint=fingerprint,
            fingerprint=fingerprint,
            state="unknown",
        )'''

content = content.replace(old, new)

with open('app/services/external_operation_service.py', 'w') as f:
    f.write(content)
print('Fixed')