with open('app/services/canonical_fingerprint.py', 'r') as f:
    content = f.read()

old = '''@dataclass
class TenantFingerprint:
    """Fingerprint for a single tenant/organization."""
    organization_id: str
    aggregate_fingerprint: str
    entity_count: int
    algorithm: FingerprintAlgorithm = FingerprintAlgorithm.SHA256_64
    metadata: Dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))'''

new = '''@dataclass
class TenantFingerprint:
    """Fingerprint for a single tenant/organization."""
    organization_id: str
    aggregate_fingerprint: str
    entity_count: int
    algorithm: FingerprintAlgorithm = FingerprintAlgorithm.SHA256_64
    metadata: Dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    components: List[ComponentFingerprint] = field(default_factory=list)'''

content = content.replace(old, new)

with open('app/services/canonical_fingerprint.py', 'w') as f:
    f.write(content)
print('Done')