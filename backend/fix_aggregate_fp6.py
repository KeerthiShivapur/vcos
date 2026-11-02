with open('app/services/canonical_fingerprint.py', 'r') as f:
    content = f.read()

# Fix the multiple @property decorators
old = '''@property
        @property
        @property
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
        return _compute_fingerprint({"tenants": parts})'''

new = '''    @property
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
        return _compute_fingerprint({"tenants": parts})'''

content = content.replace(old, new)

with open('app/services/canonical_fingerprint.py', 'w') as f:
    f.write(content)
print('Done')