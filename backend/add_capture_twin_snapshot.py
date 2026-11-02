import codecs

with codecs.open('app/intelligence/canonical_digital_twin_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add capture_twin_snapshot method before the Global instance
old_global = '''# Global instance
canonical_digital_twin_service = CanonicalDigitalTwinService()'''

new_method = '''    async def capture_twin_snapshot(
        self,
        db: AsyncSession,
        organization_id: str,
        twin_scope: str = "org",
        scope_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Capture a twin snapshot for the given organization.
        
        This is a convenience wrapper around derive_twin_state that creates
        a system-level caller for the organization.
        
        Args:
            db: Database session
            organization_id: Organization ID
            twin_scope: Scope type (org, department, team, project, person)
            scope_id: Optional scope identifier
            
        Returns:
            Twin state projection with provenance
        """
        from app.intelligence.company_context import CallerAccess
        
        # Create a system caller for the organization
        caller = CallerAccess(
            organization_id=organization_id,
            user_id="system",
            employee_id="system",
            org_wide=True,
        )
        
        return await self.derive_twin_state(
            db=db,
            caller=caller,
            scope_type=twin_scope,
            scope_id=scope_id,
        )

# Global instance'''

if old_global in content:
    content = content.replace(old_global, new_method)
    with codecs.open('app/intelligence/canonical_digital_twin_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added capture_twin_snapshot method')
else:
    print('Pattern not found')