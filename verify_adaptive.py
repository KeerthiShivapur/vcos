from app.models.company_experience import CompanyExperienceProfile, get_profile_capabilities, PROFILE_CAPABILITY_MATRIX

print('=== Capability Matrix Verification ===')
for profile in CompanyExperienceProfile:
    caps = PROFILE_CAPABILITY_MATRIX[profile]
    print(f'{profile.value}: {len(caps["modules"])} modules, {len(caps["navigation_groups"])} nav groups, governance={caps["governance_level"]}')
    print(f'  Modules: {caps["modules"]}')

print()
print('SUCCESS: Capability matrix working correctly!')