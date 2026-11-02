import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix _execute_phase to accept a skip_recording parameter
old_execute = '''    async def _execute_phase(
        self,
        db: AsyncSession,
        context: RestoreContext,
        phase_name: str,
        restore_op: RestoreOperation,
    ):
        """Execute a single restore phase with error handling."""
        phase_start = utcnow()
        phase_record = {
            "phase": phase_name,
            "started_at": utcnow().isoformat(),
            "completed_at": None,
            "passed": False,
            "message": "",
            "details": {},
            "validation_status": ValidationStatus.INCONCLUSIVE.value,
        }
        context.phases.append(phase_record)
        restore_op.phase = phase_name
        await db.flush()'''

new_execute = '''    async def _execute_phase(
        self,
        db: AsyncSession,
        context: RestoreContext,
        phase_name: str,
        restore_op: RestoreOperation,
        skip_recording: bool = False,
    ):
        """Execute a single restore phase with error handling."""
        phase_start = utcnow()
        phase_record = {
            "phase": phase_name,
            "started_at": utcnow().isoformat(),
            "completed_at": None,
            "passed": False,
            "message": "",
            "details": {},
            "validation_status": ValidationStatus.INCONCLUSIVE.value,
        }
        if not skip_recording:
            context.phases.append(phase_record)
        restore_op.phase = phase_name
        await db.flush()'''

if old_execute in content:
    content = content.replace(old_execute, new_execute)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed _execute_phase to accept skip_recording parameter')
else:
    print('Pattern not found')