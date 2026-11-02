with open('app/services/canonical_fingerprint.py', 'r') as f:
    content = f.read()

old = '''    async def compute_tenant_fingerprint(
        self,
        db: AsyncSession,
        organization_id: str,
        components: Optional[List[str]] = None,
    ) -> TenantFingerprint:
        """Compute canonical fingerprint for a single tenant."""
        self.db = db

        # This would query the canonical state for the organization
        # For now, return a mock fingerprint
        fingerprint = _compute_fingerprint({
            "organization_id": organization_id,
            "components": components or [],
        })

        return TenantFingerprint(
            organization_id=organization_id,
            aggregate_fingerprint=fingerprint,
            entity_count=0,
            algorithm=self.algorithm,
        )'''

new = '''    async def compute_tenant_fingerprint(
        self,
        db: AsyncSession,
        organization_id: str,
        components: Optional[List[str]] = None,
    ) -> TenantFingerprint:
        """Compute canonical fingerprint for a single tenant."""
        self.db = db

        # This would query the canonical state for the organization
        # For now, return a mock fingerprint with components
        components_list = components or CANONICAL_COMPONENTS
        
        # Compute fingerprint for each component
        components_fp = []
        total_entities = 0
        for comp_name in components_list:
            # In a real implementation, this would query the actual component table
            # For now, create a mock component fingerprint
            comp_fp = _compute_fingerprint({
                "organization_id": organization_id,
                "component": comp_name,
            })
            components_fp.append(ComponentFingerprint(
                component_name=comp_name,
                fingerprint=comp_fp,
                entity_count=1,  # Mock count
                last_updated=utcnow(),
            ))
            total_entities += 1
        
        # Compute aggregate fingerprint
        aggregate_fp = _compute_fingerprint({
            "organization_id": organization_id,
            "components": [c.fingerprint for c in components_fp],
        })

        return TenantFingerprint(
            organization_id=organization_id,
            aggregate_fingerprint=aggregate_fp,
            entity_count=total_entities,
            algorithm=self.algorithm,
            components=components_fp,
        )'''

content = content.replace(old, new)

with open('app/services/canonical_fingerprint.py', 'w') as f:
    f.write(content)
print('Done')