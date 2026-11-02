import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add more debug logging around BackupManifest creation
old_manifest = '''        backup_metadata = BackupManifest(
            id=backup_id,
            organization_id=org.id,
            backup_kind=BackupKind.FULL,
            status=BackupStatus.VERIFIED,
            started_at=utcnow(),
            completed_at=utcnow(),
            retention_days=30,
            expires_at=utcnow() + timedelta(days=30),
            backup_format="mock",
            backup_size_bytes=1024 * 1024 * 100,  # 100 MB mock
            checksum_sha256=hashlib.sha256("mock-backup-{}".format(utcnow().isoformat()).encode()).hexdigest()[:64],
            tables_included=[
                "organizations", "users", "employees", "departments", "teams",
                "projects", "tasks", "company_decisions", "company_actions",
                "company_commitments", "company_authorizations",
                "company_objectives", "company_goals",
                "canonical_operations", "operation_attempts",
                "organizational_learning", "canonical_observations",
            ],
        )
        db_session.add(backup_metadata)
        await db_session.flush()
        await db_session.commit()
        print("DEBUG: BackupManifest committed")'''

new_manifest = '''        print("DEBUG: Creating BackupManifest with organization_id={}".format(org.id))
        backup_metadata = BackupManifest(
            id=backup_id,
            organization_id=org.id,
            backup_kind=BackupKind.FULL,
            status=BackupStatus.VERIFIED,
            started_at=utcnow(),
            completed_at=utcnow(),
            retention_days=30,
            expires_at=utcnow() + timedelta(days=30),
            backup_format="mock",
            backup_size_bytes=1024 * 1024 * 100,  # 100 MB mock
            checksum_sha256=hashlib.sha256("mock-backup-{}".format(utcnow().isoformat()).encode()).hexdigest()[:64],
            tables_included=[
                "organizations", "users", "employees", "departments", "teams",
                "projects", "tasks", "company_decisions", "company_actions",
                "company_commitments", "company_authorizations",
                "company_objectives", "company_goals",
                "canonical_operations", "operation_attempts",
                "organizational_learning", "canonical_observations",
            ],
        )
        db_session.add(backup_metadata)
        await db_session.flush()
        print("DEBUG: BackupManifest flushed, checking organization_id...")
        # Verify the organization_id in the database
        from sqlalchemy import select
        check = await db_session.execute(select(BackupManifest.organization_id).where(BackupManifest.id == backup_id))
        check_org_id = check.scalar()
        print("DEBUG: BackupManifest organization_id in DB: {}".format(check_org_id))
        await db_session.commit()
        print("DEBUG: BackupManifest committed")'''

if old_manifest in content:
    content = content.replace(old_manifest, new_manifest)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging for BackupManifest creation')
else:
    print('Pattern not found')