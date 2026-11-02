with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the indentation issue around PHASE 12
old = """        # =====================================================================
        # PHASE 12: RPO/RTO MEASUREMENT
        # =====================================================================
logger.info("=== PHASE 12: RPO/RTO MEASUREMENT ===")
    measurement_service = RPORTOMeasurementService()
    """

new = """        # =====================================================================
        # PHASE 12: RPO/RTO MEASUREMENT
        # =====================================================================
        logger.info("=== PHASE 12: RPO/RTO MEASUREMENT ===")
        measurement_service = RPORTOMeasurementService()
"""

content = content.replace(old, new)

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed indentation")