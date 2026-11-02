with open('app/services/canonical_fingerprint.py', 'r') as f:
    content = f.read()

# Find the get_tenant method and add the aggregate_fingerprint property after it
idx = content.find('def get_tenant(self, organization_id: str)')
if idx >= 0:
    # Find the end of the get_tenant method
    idx2 = content.find('\n\n', idx)
    if idx2 == -1:
        idx2 = len(content)
    else:
        idx2 += 2  # Include the newlines
    
    # Insert the aggregate_fingerprint property after get_tenant
    new_method = '''
    @property
    def aggregate_fingerprint(self) -> str:
        """Compute aggregate fingerprint from all tenant fingerprints."""
        if not self.tenants:
            return _compute_fingerprint({"empty": True})
        
        # Sort tenant fingerprints by organization_id for determinism
        sorted_tenants = sorted(self.tenants, key=lambda t: t.organization_id)
        parts = []
        for tenant in sorted_tenants:
            parts.append(f"{tenant.organization_id}:{tenant.aggregate_fingerprint}")
        combined = "|".join(parts)
        return _compute_fingerprint({"tenants": parts})
'''
    content = content[:idx2] + new_method + content[idx2:]
    
    with open('app/services/canonical_fingerprint.py', 'w') as f:
        f.write(content)
    print('Done')
else:
    print('Not found')