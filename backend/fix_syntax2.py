with open('app/services/release_failure_recovery.py', 'r') as f:
    content = f.read()

# Fix duplicate initiated_by parameter
old = '''        recovery = ReleaseRecoveryRecord(
            release_id=release.id,
            organization_id=release.organization_id,
            recovery_strategy=recovery_strategy.value,
            recovery_reason=f"Recovery from {release.failure_type}: {release.error}",
            status="pending",
            initiated_by=initiated_by,
            steps=[],
            steps_total=0,
            pre_recovery_fingerprint=release.post_release_fingerprint,
            governance_required=governance_required,
            governance_status="pending" if governance_required else "not_required",
            initiated_by=initiated_by,
        )'''

new = '''        recovery = ReleaseRecoveryRecord(
            release_id=release.id,
            organization_id=release.organization_id,
            recovery_strategy=recovery_strategy.value,
            recovery_reason=f"Recovery from {release.failure_type}: {release.error}",
            status="pending",
            initiated_by=initiated_by,
            steps=[],
            steps_total=0,
            pre_recovery_fingerprint=release.post_release_fingerprint,
            governance_required=governance_required,
            governance_status="pending" if governance_required else "not_required",
        )'''

content = content.replace(old, new)

with open('app/services/release_failure_recovery.py', 'w') as f:
    f.write(content)
print('Done')