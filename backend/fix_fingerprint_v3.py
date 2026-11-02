with open('app/services/external_operation_service.py', 'r') as f:
    content = f.read()

# Fix _mark_unknown to set both fingerprint and request_fingerprint
old = '''        # Create ExternalUnknownState record for reconciliation
        from app.models.canonical_reliability import ExternalUnknownState
        import hashlib
        import json
        fingerprint_data = json.dumps({
            "organization_id": operation.organization_id,
            "operation_id": operation.id,
            "external_system": "connector",
            "operation_type": operation.operation_type,
            "target_external_id": operation.target_external_id,
            "payload": operation.payload,
        }, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]
        
        unknown = ExternalUnknownState(
            organization_id=operation.organization_id,
            operation_id=operation.id,
            external_system="connector",
            external_operation_id=operation.external_operation_id or f"local-{operation.id}",
            external_operation_type=operation.operation_type,
            request_payload_json=operation.payload,
            request_fingerprint=fingerprint,
            state="unknown",
        )'''

new = '''        # Create ExternalUnknownState record for reconciliation
        from app.models.canonical_reliability import ExternalUnknownState
        import hashlib
        import json
        fingerprint_data = json.dumps({
            "organization_id": operation.organization_id,
            "operation_id": operation.id,
            "external_system": "connector",
            "operation_type": operation.operation_type,
            "target_external_id": operation.target_external_id,
            "payload": operation.payload,
        }, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]
        
        unknown = ExternalUnknownState(
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