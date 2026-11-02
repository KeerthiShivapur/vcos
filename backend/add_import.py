with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Add the import after line 100 (canonical_company_continuity_service import)
lines.insert(101, 'from app.services.canonical_reality_integrity_service import canonical_reality_integrity_service\n')

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Added import")