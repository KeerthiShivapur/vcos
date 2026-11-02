import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add the _test_manipulated_manifest_skip method
old_method = '''    async def _test_manipulated_backup_manifest(self, result: ValidationResult, db: AsyncSession, organization_id: str) -> None:
        """Test restore with manipulated backup manifest."""'''

new_method = '''    async def _test_manipulated_manifest_skip(self, result: ValidationResult, db: AsyncSession, organization_id: str) -> None:
        """Test restore with manipulated backup manifest (with skip_recording)."""
        await self._test_manipulated_backup_manifest(result, db, organization_id, skip_recording=True)

    async def _test_manipulated_backup_manifest(self, result: ValidationResult, db: AsyncSession, organization_id: str, skip_recording: bool = False) -> None:'''

if old_method in content:
    content = content.replace(old_method, new_method)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added _test_manipulated_manifest_skip method')
else:
    print('Pattern not found')