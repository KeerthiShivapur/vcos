import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging to _phase_backup_selected
old_phase = '''    async def _phase_backup_selected(self, db: AsyncSession, context: RestoreContext, restore_op: RestoreOperation) -> Dict[str, Any]:
        """Phase 1: Verify backup exists and is selectable."""
        backup = await db.get(BackupManifest, context.backup_id)
        if not backup:
            return {"passed": False, "message": f"Backup {context.backup_id} not found", "validation_status": ValidationStatus.FAILED.value}
        
        if backup.status not in (BackupStatus.COMPLETED, BackupStatus.VERIFIED):
            return {"passed": False, "message": f"Backup {context.backup_id} is not completed or verified (status: {backup.status})", "validation_status": ValidationStatus.FAILED.value}
        
        # Verify backup belongs to the organization (tenant isolation)
        if backup.organization_id != context.organization_id:
            return {"passed": False, "message": f"Backup belongs to organization {backup.organization_id}, not {context.organization_id}", "validation_status": ValidationStatus.FAILED.value}'''

new_phase = '''    async def _phase_backup_selected(self, db: AsyncSession, context: RestoreContext, restore_op: RestoreOperation) -> Dict[str, Any]:
        """Phase 1: Verify backup exists and is selectable."""
        print("DEBUG RESTORE: _phase_backup_selected called with backup_id={}, org_id={}".format(context.backup_id, context.organization_id))
        backup = await db.get(BackupManifest, context.backup_id)
        print("DEBUG RESTORE: Fetched backup: id={}, org_id={}, status={}".format(backup.id if backup else None, backup.organization_id if backup else None, backup.status if backup else None))
        if not backup:
            return {"passed": False, "message": f"Backup {context.backup_id} not found", "validation_status": ValidationStatus.FAILED.value}
        
        if backup.status not in (BackupStatus.COMPLETED, BackupStatus.VERIFIED):
            return {"passed": False, "message": f"Backup {context.backup_id} is not completed or verified (status: {backup.status})", "validation_status": ValidationStatus.FAILED.value}
        
        # Verify backup belongs to the organization (tenant isolation)
        print("DEBUG RESTORE: Checking org_id: backup.org_id={}, context.org_id={}".format(backup.organization_id, context.organization_id))
        if backup.organization_id != context.organization_id:
            return {"passed": False, "message": f"Backup belongs to organization {backup.organization_id}, not {context.organization_id}", "validation_status": ValidationStatus.FAILED.value}'''

if old_phase in content:
    content = content.replace(old_phase, new_phase)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging to restore service')
else:
    print('Pattern not found')