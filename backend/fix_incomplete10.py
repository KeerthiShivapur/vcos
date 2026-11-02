with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the incomplete restore test and fix it
old_text = '''    @pytest.mark.asyncio
    @pytest.mark.postgres
    async def test_incomplete_restore_rejection_real_pg(self, pg_db_session, production_company_real_pg):
        """Test that incomplete restore is not marked as ready."""
        
        logger.info("=== Incomplete Restore Rejection Test (Real PostgreSQL) ===")
        
        org = production_company_real_pg["organization"]
        org_id = org.id
        
        # Attempt restore with nonexistent backup - should fail at BACKUP_SELECTED phase
        with pytest.raises(Exception) as exc_info:
            # The restore should fail at BACKUP_SELECTED phase
            await restore_service.restore_from_backup(
                db=pg_db_session,
                backup_id="nonexistent-backup",
                organization_id=org_id,
                initiated_by="fail_test",
            )
        
       '''

new_text = '''    @pytest.mark.asyncio
    @pytest.mark.postgres
    async def test_incomplete_restore_rejection_real_pg(self, pg_db_session, production_company_real_pg):
        """Test that incomplete restore is not marked as ready."""
        
        logger.info("=== Incomplete Restore Rejection Test (Real PostgreSQL) ===")
        
        org = production_company_real_pg["organization"]
        org_id = org.id
        
        # Attempt restore with nonexistent backup - should fail at BACKUP_SELECTED phase
        result = await restore_service.restore_from_backup(
            db=pg_db_session,
            backup_id="nonexistent-backup",
            organization_id=org_id,
            initiated_by="fail_test",
        )
        
        assert result["success"] is False
        assert "not found" in result["error"].lower() or "backup" in result["error"].lower()
        
        logger.info("✅ Incomplete restore correctly rejected on real PostgreSQL")'''

content = content.replace(
    '''    @pytest.mark.asyncio
    @pytest.mark.postgres
    async def test_incomplete_restore_rejection_real_pg(self, pg_db_session, production_company_real_pg):
        """Test that incomplete restore is not marked as ready."""
        
        logger.info("=== Incomplete Restore Rejection Test (Real PostgreSQL) ===")
        
        org = production_company_real_pg["organization"]
        org_id = org.id
        
        # Attempt restore with nonexistent backup - should fail at BACKUP_SELECTED phase
        with pytest.raises(Exception) as exc_info:
            # The restore should fail at BACKUP_SELECTED phase
            await restore_service.restore_from_backup(
                db=pg_db_session,
                backup_id="nonexistent-backup",
                organization_id=org_id,
                initiated_by="fail_test",
            )
        
       ''',
    new_text)

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed")