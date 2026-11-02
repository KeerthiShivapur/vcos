with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the entire RPO/RTO measurement section from line 1105 onwards
old_section = """        # =====================================================================
        # PHASE 12: RPO/RTO MEASUREMENT
        # =====================================================================
        logger.info("=== PHASE 12: RPO/RTO MEASUREMENT ===")
        measurement_service = RPORTOMeasurementService()
        
        # Start measurement with disaster time
        disaster_time = utcnow()
        measurement_service.start_measurement(
            recovery_id=backup_id,
            disaster_time=disaster_time,
            backup_id=backup_id,
            environment="test",
            scale_profile="startup",
        )
        
        # Simulate backup metadata
        backup_size = 1024 * 1024 * 100  # 100 MB
        measurement_service.record_backup_metadata(backup_id, backup_size)
        measurement_service.record_dataset_size(backup_size)
        measurement_service.record_latest_recoverable_time(disaster_time)
        
        # Record restore phases
        measurement_service.record_phase(RecoveryPhase.DATABASE_RESTORED, utcnow())
        measurement_service.record_phase(RecoveryPhase.SCHEMA_VALIDATED, utcnow())
        measurement_service.record_phase(RecoveryPhase.CANONICAL_INTEGRITY_VALIDATED, utcnow())
        measurement_service.record_phase(RecoveryPhase.ACTIVATED, utcnow())
        measurement_service.record_phase(RecoveryPhase.OPERATIONAL, utcnow())
        
        # Record backup metadata
        measurement_service.record_backup_metadata(backup_id, backup_size)
        
        final_measurement = measurement_service.complete_measurement(
            success=True,
            validation_results={"checksum": "passed", "schema": "passed"},
        )
        
        rpo_seconds = final_measurement.rpo_seconds
        rto_seconds = final_measurement.rto_seconds
        
        if rpo_seconds is not None:
            logger.info(f"RPO: {rpo_seconds:.1f} seconds ({rpo_seconds/60:.1f} minutes)")
            assert rpo_seconds < 3600, f"RPO too high: {rpo_seconds/60:.1f} minutes"
        else:
            logger.info("RPO: Not measured in this environment")
        
        if rto_seconds is not None:
            logger.info(f"RTO: {rto_seconds:.1f} seconds ({rto_seconds/60:.1f} minutes)")
            assert rto_seconds < 7200, f"RTO too high: {rto_seconds/60:.1f} minutes"
        else:
            logger.info("RTO: Not measured in this environment")
        
        logger.info("✅ RPO/RTO measured and within targets")"""

new_section = """        # =====================================================================
        # PHASE 12: RPO/RTO MEASUREMENT
        # =====================================================================
        logger.info("=== PHASE 12: RPO/RTO MEASUREMENT ===")
        measurement_service = RPORTOMeasurementService()
        
        # Start measurement with disaster time
        disaster_time = utcnow()
        measurement_service.start_measurement(
            recovery_id=backup_id,
            disaster_time=disaster_time,
            backup_id=backup_id,
            environment="test",
            scale_profile="startup",
        )
        
        # Simulate backup metadata
        backup_size = 1024 * 1024 * 100  # 100 MB
        measurement_service.record_backup_metadata(backup_id, backup_size)
        measurement_service.record_dataset_size(backup_size)
        measurement_service.record_latest_recoverable_time(disaster_time)
        
        # Record restore phases
        measurement_service.record_phase(RecoveryPhase.DATABASE_RESTORED, utcnow())
        measurement_service.record_phase(RecoveryPhase.SCHEMA_VALIDATED, utcnow())
        measurement_service.record_phase(RecoveryPhase.CANONICAL_INTEGRITY_VALIDATED, utcnow())
        measurement_service.record_phase(RecoveryPhase.ACTIVATED, utcnow())
        measurement_service.record_phase(RecoveryPhase.OPERATIONAL, utcnow())
        
        # Record backup metadata
        measurement_service.record_backup_metadata(backup_id, backup_size)
        
        final_measurement = measurement_service.complete_measurement(
            success=True,
            validation_results={"checksum": "passed", "schema": "passed"},
        )
        
        rpo_seconds = final_measurement.rpo_seconds
        rto_seconds = final_measurement.rto_seconds
        
        if rpo_seconds is not None:
            logger.info(f"RPO: {rpo_seconds:.1f} seconds ({rpo_seconds/60:.1f} minutes)")
            assert rpo_seconds < 3600, f"RPO too high: {rpo_seconds/60:.1f} minutes"
        else:
            logger.info("RPO: Not measured in this environment")
        
        if rto_seconds is not None:
            logger.info(f"RTO: {rto_seconds:.1f} seconds ({rto_seconds/60:.1f} minutes)")
            assert rto_seconds < 7200, f"RTO too high: {rto_seconds/60:.1f} minutes"
        else:
            logger.info("RTO: Not measured in this environment")
        
        logger.info("✅ RPO/RTO measured and within targets")"""

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(old_section, new_section)

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Replaced entire RPO/RTO section")