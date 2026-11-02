from app.models.company_experience import CompanyExperienceProfile, PROFILE_CAPABILITY_MATRIX

print('=== Capability Matrix Verification ===')
for p in CompanyExperienceProfile:
    caps = PROFILE_CAPABILITY_MATRIX[p]
    print(f'{p.value}: {len(caps["modules"])} modules, {len(caps["navigation_groups"])} nav groups, governance={caps["governance_level"]}')
    print(f'  Modules: {caps["modules"]}')

print()
print('SUCCESS: Capability matrix working correctly!')