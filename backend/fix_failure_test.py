with open('tests/acceptance/test_backup_restore_roundtrip.py', 'r') as f:
    content = f.read()

# Fix the failure test
old = '''    @pytest.mark.asyncio
    async def test_restore_failure_handled(self, db_session: AsyncSession):
        """Test that restore failures are properly handled."""
        from app.services.restore_service import restore_service, RestoreStatus
        
        # Try to restore from non-existent backup
        result = await restore_service.restore_from_backup(
            db=db_session,
            backup_id="non-existent-backup",
            organization_id="test-org",
            initiated_by="test",
        )
        # Should fail gracefully
        assert result["success"] is False'''

new = '''    @pytest.mark.asyncio
    async def test_restore_failure_handled(self, db_session: AsyncSession):
        """Test that restore failures are properly handled."""
        from app.services.restore_service import restore_service, RestoreStatus
        
        # Try to restore from non-existent backup
        result = await restore_service.restore_from_backup(
            db=db_session,
            backup_id="non-existent-backup",
            organization_id="test-org",
            initiated_by="test",
        )
        # Should fail gracefully
        assert result["success"] is False
        assert "not found" in result.get("error", "").lower()'''

content = content.replace(old, new)

with open('tests/acceptance/test_backup_restore_roundtrip.py', 'w') as f:
    f.write(content)

print('Fixed failure test')