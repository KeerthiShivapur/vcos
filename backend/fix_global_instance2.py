import codecs

with codecs.open('app/intelligence/canonical_digital_twin_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the end of the file
old_end = 'async def capture_twin_snapshot(\n        self,\n        db: AsyncSession,\n        organization_id: str,\n        twin_scope: str = "org",\n        scope_id: Optional[str] = None,\n    ) -> Dict[str, Any]:\n        """Capture a twin snapshot for the given organization.\n        \n        This is a convenience wrapper around derive_twin_state that creates\n        a system-level caller for the organization.\n        \n        Args:\n            db: Database session\n            organization_id: Organization ID\n            twin_scope: Scope type (org, department, team, project, person)\n            scope_id: Optional scope identifier\n            \n        Returns:\n            Twin state projection with provenance\n        """\n        from app.intelligence.company_context import CallerAccess\n        \n        # Create a system caller for the organization\n        caller = CallerAccess(\n            organization_id=organization_id,\n            user_id="system",\n            employee_id="system",\n            org_wide=True,\n        )\n        \n        return await self.derive_twin_state(\n            db=db,\n            caller=caller,\n            scope_type=twin_scope,\n            scope_id=scope_id,\n        )\n\n# Global instance'

new_end = '''        return await self.derive_twin_state(
            db=db,
            caller=caller,
            scope_type=twin_scope,
            scope_id=scope_id,
        )

# Global instance
canonical_digital_twin_service = CanonicalDigitalTwinService()'''

if old_end in content:
    content = content.replace(old_end, new_end)
    with codecs.open('app/intelligence/canonical_digital_twin_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added global instance')
else:
    print('Pattern not found')
    # Debug: show the end of the file
    with codecs.open('app/intelligence/canonical_digital_twin_service.py', 'r', encoding='utf-8') as f:
        content = f.read()
    print(repr(content[-500:]))