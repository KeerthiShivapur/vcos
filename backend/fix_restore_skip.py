import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add skip_recording parameter to restore_from_backup
old_restore_sig = '''    async def restore_from_backup(
        self,
        db: AsyncSession,
        backup_id: str,
        organization_id: str,
        initiated_by: str,
        target_time: Optional[datetime] = None,
        target_version: Optional[int] = None,
    ) -> Dict[str, Any]:'''

new_restore_sig = '''    async def restore_from_backup(
        self,
        db: AsyncSession,
        backup_id: str,
        organization_id: str,
        initiated_by: str,
        target_time: Optional[datetime] = None,
        target_version: Optional[int] = None,
        skip_recording: bool = False,
    ) -> Dict[str, Any]:'''

if old_restore_sig in content:
    content = content.replace(old_restore_sig, new_restore_sig)
    print('Updated restore_from_backup signature')
else:
    print('Signature pattern not found')

# Update the _execute_phase calls in restore_from_backup
old_loop = '''        try:
            for phase_name in PHASE_ORDER:
                await self._execute_phase(db, context, phase_name, restore_op)'''

new_loop = '''        try:
            for phase_name in PHASE_ORDER:
                await self._execute_phase(db, context, phase_name, restore_op, skip_recording=skip_recording)'''

if old_loop in content:
    content = content.replace(old_loop, new_loop)
    print('Updated _execute_phase calls in restore_from_backup')
else:
    print('Loop pattern not found')

with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')