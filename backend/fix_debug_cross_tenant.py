import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging to _test_cross_tenant_restore_attempt
old_cross = '''    async def _test_cross_tenant_restore_attempt(
        self,
        result: ValidationResult,
        db: AsyncSession,
        organization_id: str,
    ) -> None:
        """Test that restore cannot be initiated for another tenant's backup."""
        try:
            # Create a second organization
            from app.models.organization import Organization
            import uuid
            
            other_org = Organization(
                id=f"other-{uuid.uuid4().hex[:8]}",
                name="Other Test Org",
                slug=f"other-{uuid.uuid4().hex[:8]}",
                status="active",
            )
            db.add(other_org)
            await db.flush()
            
            # Create a backup for the other organization
            from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
            other_backup = BackupManifest(
                id=f"bkp-other-{uuid.uuid4().hex[:8]}",
                organization_id=other_org.id,
                backup_kind=BackupKind.FULL,
                status=BackupStatus.VERIFIED,
                started_at=utcnow() - timedelta(hours=1),
                completed_at=utcnow(),
                backup_size_bytes=1024 * 1024 * 100,
                checksum_sha256="a" * 64,
                retention_days=30,
            )
            db.add(other_backup)
            await db.flush()
            
            # Attempt to restore other org's backup into this organization
            # This should fail due to tenant isolation
            try:
                restore_result = await self.restore_from_backup(
                    db=db,
                    backup_id=other_backup.id,
                    organization_id=organization_id,
                    initiated_by="adversarial_test",
                )'''

new_cross = '''    async def _test_cross_tenant_restore_attempt(
        self,
        result: ValidationResult,
        db: AsyncSession,
        organization_id: str,
    ) -> None:
        """Test that restore cannot be initiated for another tenant's backup."""
        try:
            # Create a second organization
            from app.models.organization import Organization
            import uuid
            
            other_org = Organization(
                id=f"other-{uuid.uuid4().hex[:8]}",
                name="Other Test Org",
                slug=f"other-{uuid.uuid4().hex[:8]}",
                status="active",
            )
            db.add(other_org)
            await db.flush()
            
            # Create a backup for the other organization
            from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
            other_backup = BackupManifest(
                id=f"bkp-other-{uuid.uuid4().hex[:8]}",
                organization_id=other_org.id,
                backup_kind=BackupKind.FULL,
                status=BackupStatus.VERIFIED,
                started_at=utcnow() - timedelta(hours=1),
                completed_at=utcnow(),
                backup_size_bytes=1024 * 1024 * 100,
                checksum_sha256="a" * 64,
                retention_days=30,
            )
            db.add(other_backup)
            await db.flush()
            
            # Attempt to restore other org's backup into this organization
            # This should fail due to tenant isolation
            print("DEBUG CROSS: Attempting cross-tenant restore with backup_id={}".format(other_backup.id))
            try:
                restore_result = await self.restore_from_backup(
                    db=db,
                    backup_id=other_backup.id,
                    organization_id=organization_id,
                    initiated_by="adversarial_test",
                )
                print("DEBUG CROSS: restore_from_backup returned: {}".format(restore_result))
                if restore_result.get("success", False):
                    result.add_check(ValidationCheck(
                        name="cross_tenant_restore_attempt",
                        status=ValidationStatus.FAILED,
                        message="Cross-tenant restore unexpectedly succeeded",
                        details={"other_backup_id": other_backup.id},
                    ))
                else:
                    result.add_check(ValidationCheck(
                        name="cross_tenant_restore_attempt",
                        status=ValidationStatus.VERIFIED,
                        message="Cross-tenant restore correctly rejected",
                        details={"other_backup_id": other_backup.id},
                    ))
            except Exception as e:
                print("DEBUG CROSS: Caught exception: {}".format(e))
                # Expected - restore should fail
                result.add_check(ValidationCheck(
                    name="cross_tenant_restore_attempt",
                    status=ValidationStatus.VERIFIED,
                    message="Cross-tenant restore correctly rejected",
                    details={"error": str(e)},
                ))'''

if old_cross in content:
    content = content.replace(old_cross, new_cross)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging to cross-tenant test')
else:
    print('Pattern not found')