with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix lines 1105-1160 (the entire PHASE 12 section)
# Replace lines 1105-1160 with properly indented version
new_lines = [
    '        # =====================================================================\n',
    '        # PHASE 12: RPO/RTO MEASUREMENT\n',
    '        # =====================================================================\n',
    '        logger.info("=== PHASE 12: RPO/RTO MEASUREMENT ===")\n',
    '        measurement_service = RPORTOMeasurementService()\n',
    '\n',
    '        # Start measurement with disaster time\n',
    '        disaster_time = utcnow()\n',
    '        measurement_service.start_measurement(\n',
    '            recovery_id=backup_id,\n',
    '            disaster_time=disaster_time,\n',
    '            backup_id=backup_id,\n',
    '            environment="test",\n',
    '            scale_profile="startup",\n',
    '        )\n',
    '\n',
    '        # Simulate backup metadata\n',
    '        backup_size = 1024 * 1024 * 100  # 100 MB\n',
    '        measurement_service.record_backup_metadata(backup_id, backup_size)\n',
    '        measurement_service.record_dataset_size(backup_size)\n',
    '        measurement_service.record_latest_recoverable_time(disaster_time)\n',
    '\n',
    '        # Record restore phases\n',
    '        measurement_service.record_phase(RecoveryPhase.DATABASE_RESTORED, utcnow())\n',
    '        measurement_service.record_phase(RecoveryPhase.SCHEMA_VALIDATED, utcnow())\n',
    '        measurement_service.record_phase(RecoveryPhase.CANONICAL_INTEGRITY_VALIDATED, utcnow())\n',
    '        measurement_service.record_phase(RecoveryPhase.ACTIVATED, utcnow())\n',
    '        measurement_service.record_phase(RecoveryPhase.OPERATIONAL, utcnow())\n',
    '\n',
    '        # Record backup metadata\n',
    '        measurement_service.record_backup_metadata(backup_id, backup_size)\n',
    '\n',
    '        final_measurement = measurement_service.complete_measurement(\n',
    '            success=True,\n',
    '            validation_results={"checksum": "passed", "schema": "passed"},\n',
    '        )\n',
    '\n',
    '        rpo_seconds = final_measurement.rpo_seconds\n',
    '        rto_seconds = final_measurement.rto_seconds\n',
    '\n',
    '        if rpo_seconds is not None:\n',
    '            logger.info(f"RPO: {rpo_seconds:.1f} seconds ({rpo_seconds/60:.1f} minutes)")\n',
    '            assert rpo_seconds < 3600, f"RPO too high: {rpo_seconds/60:.1f} minutes"\n',
    '        else:\n',
    '            logger.info("RPO: Not measured in this environment")\n',
    '\n',
    '        if rto_seconds is not None:\n',
    '            logger.info(f"RTO: {rto_seconds:.1f} seconds ({rto_seconds/60:.1f} minutes)")\n',
    '            assert rto_seconds < 7200, f"RTO too high: {rto_seconds/60:.1f} minutes"\n',
    '        else:\n',
    '            logger.info("RTO: Not measured in this environment")\n',
    '\n',
    '        logger.info("✅ RPO/RTO measured and within targets")\n',
]

# Find the start and end of the PHASE 12 section
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if 'PHASE 12: RPO/RTO MEASUREMENT' in line and '===' in line:
        start_idx = i - 3  # Include the comment lines before
        break

if start_idx is not None:
    # Find the end - look for "PHASE 13"
    for i in range(start_idx, len(lines)):
        if 'PHASE 13:' in lines[i]:
            end_idx = i
            break
    
    if end_idx is not None:
        # Replace the section
        new_lines_list = [
            '        # =====================================================================\n',
            '        # PHASE 12: RPO/RTO MEASUREMENT\n',
            '        # =====================================================================\n',
            '        logger.info("=== PHASE 12: RPO/RTO MEASUREMENT ===")\n',
            '        measurement_service = RPORTOMeasurementService()\n',
            '\n',
            '        # Start measurement with disaster time\n',
            '        disaster_time = utcnow()\n',
            '        measurement_service.start_measurement(\n',
            '            recovery_id=backup_id,\n',
            '            disaster_time=disaster_time,\n',
            '            backup_id=backup_id,\n',
            '            environment="test",\n',
            '            scale_profile="startup",\n',
            '        )\n',
            '\n',
            '        # Simulate backup metadata\n',
            '        backup_size = 1024 * 1024 * 100  # 100 MB\n',
            '        measurement_service.record_backup_metadata(backup_id, backup_size)\n',
            '        measurement_service.record_dataset_size(backup_size)\n',
            '        measurement_service.record_latest_recoverable_time(disaster_time)\n',
            '\n',
            '        # Record restore phases\n',
            '        measurement_service.record_phase(RecoveryPhase.DATABASE_RESTORED, utcnow())\n',
            '        measurement_service.record_phase(RecoveryPhase.SCHEMA_VALIDATED, utcnow())\n',
            '        measurement_service.record_phase(RecoveryPhase.CANONICAL_INTEGRITY_VALIDATED, utcnow())\n',
            '        measurement_service.record_phase(RecoveryPhase.ACTIVATED, utcnow())\n',
            '        measurement_service.record_phase(RecoveryPhase.OPERATIONAL, utcnow())\n',
            '\n',
            '        # Record backup metadata\n',
            '        measurement_service.record_backup_metadata(backup_id, backup_size)\n',
            '\n',
            '        final_measurement = measurement_service.complete_measurement(\n',
            '            success=True,\n',
            '            validation_results={"checksum": "passed", "schema": "passed"},\n',
            '        )\n',
            '\n',
            '        rpo_seconds = final_measurement.rpo_seconds\n',
            '        rto_seconds = final_measurement.rto_seconds\n',
            '\n',
            '        if rpo_seconds is not None:\n',
            '            logger.info(f"RPO: {rpo_seconds:.1f} seconds ({rpo_seconds/60:.1f} minutes)")\n',
            '            assert rpo_seconds < 3600, f"RPO too high: {rpo_seconds/60:.1f} minutes"\n',
            '        else:\n',
            '            logger.info("RPO: Not measured in this environment")\n',
            '\n',
            '        if rto_seconds is not None:\n',
            '            logger.info(f"RTO: {rto_seconds:.1f} seconds ({rto_seconds/60:.1f} minutes)")\n',
            '            assert rto_seconds < 7200, f"RTO too high: {rto_seconds/60:.1f} minutes"\n',
            '        else:\n',
            '            logger.info("RTO: Not measured in this environment")\n',
            '\n',
            '        logger.info("✅ RPO/RTO measured and within targets")\n',
        ]
        
        lines[start_idx:end_idx] = new_lines
        
        with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print("Fixed PHASE 12 section")
    else:
        print("Could not find end of section")
else:
    print("Could not find start of section")