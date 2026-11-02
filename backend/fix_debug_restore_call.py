import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging before restore call
old_restore = '''        logger.info("Company Continuity - Backup created and verified: {}".format(backup_id))
        
        # =====================================================================
        # PHASE 9: CANONICAL FINGERPRINT BEFORE DISASTER
        # =====================================================================
        logger.info("=== PHASE 9: CANONICAL FINGERPRINT BEFORE DISASTER ===")
        fingerprint_calculator = CanonicalFingerprint(db_session, org.id)
        pre_disaster_fingerprint = await fingerprint_calculator.compute()
        pre_disaster_details = await fingerprint_calculator.compute_detailed()
        
        logger.info("Pre-disaster canonical fingerprint: {}".format(pre_disaster_fingerprint))
        logger.info("Pre-disaster entity counts: {}".format(pre_disaster_details['counts']))
        
        # =====================================================================
        # PHASE 10: DISASTER SIMULATION
        # =====================================================================
        logger.info("=== PHASE 10: DISASTER SIMULATION ===")
        
        disaster = await disaster_recovery_service.detect_disaster(
            db=db_session,
            disaster_type=DisasterType.DB_CORRUPTION,
            severity=DisasterSeverity.CRITICAL,
            organization_id=org.id,
            affected_systems=["postgresql-primary", "application-workers"],
            affected_tenants=[org.id],
            error="Simulated database corruption for DR test",
            metadata={"test": True, "backup_id": backup_id},
        )'''

new_restore = '''        print("DEBUG: About to call restore with backup_id={}".format(backup_id))
        print("DEBUG: org.id for restore = {}".format(org.id))
        logger.info("Company Continuity - Backup created and verified: {}".format(backup_id))
        
        # =====================================================================
        # PHASE 9: CANONICAL FINGERPRINT BEFORE DISASTER
        # =====================================================================
        logger.info("=== PHASE 9: CANONICAL FINGERPRINT BEFORE DISASTER ===")
        fingerprint_calculator = CanonicalFingerprint(db_session, org.id)
        pre_disaster_fingerprint = await fingerprint_calculator.compute()
        pre_disaster_details = await fingerprint_calculator.compute_detailed()
        
        logger.info("Pre-disaster canonical fingerprint: {}".format(pre_disaster_fingerprint))
        logger.info("Pre-disaster entity counts: {}".format(pre_disaster_details['counts']))
        
        # =====================================================================
        # PHASE 10: DISASTER SIMULATION
        # =====================================================================
        logger.info("=== PHASE 10: DISASTER SIMULATION ===")
        
        disaster = await disaster_recovery_service.detect_disaster(
            db=db_session,
            disaster_type=DisasterType.DB_CORRUPTION,
            severity=DisasterSeverity.CRITICAL,
            organization_id=org.id,
            affected_systems=["postgresql-primary", "application-workers"],
            affected_tenants=[org.id],
            error="Simulated database corruption for DR test",
            metadata={"test": True, "backup_id": backup_id},
        )'''

if old_restore in content:
    content = content.replace(old_restore, new_restore)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging before restore')
else:
    print('Pattern not found')