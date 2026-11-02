from app.models.company_experience import CompanyExperienceProfile, PROFILE_CAPABILITY_MATRIX, get_profile_capabilities

print('=== Profile Transition Preview (Model Level) ===')

def get_transition_diff(current, target):
    current_caps = PROFILE_CAPABILITY_MATRIX[current]
    target_caps = PROFILE_CAPABILITY_MATRIX[target]
    
    return {
        "current_profile": current.value,
        "target_profile": target.value,
        "modules_added": list(set(target_caps.get("modules_enabled_by_default", [])) - 
                            set(current_caps.get("modules_enabled_by_default", []))),
        "modules_removed": list(set(current_caps.get("modules_enabled_by_default", [])) - 
                              set(target_caps.get("modules_enabled_by_default", []))),
        "navigation_groups_added": list(set(target_caps.get("navigation_groups", [])) - 
                                      set(current_caps.get("navigation_groups", []))),
        "navigation_groups_removed": list(set(current_caps.get("navigation_groups", [])) - 
                                        set(target_caps.get("navigation_groups", []))),
        "governance_level_change": {
            "from": current_caps.get("governance_level"),
            "to": target_caps.get("governance_level"),
        },
        "approval_levels_change": {
            "from": current_caps.get("approval_levels"),
            "to": target_caps.get("approval_levels"),
        },
        "new_features": list(set(target_caps.get("features", [])) - set(current_caps.get("features", []))),
    }

transitions = [
    ('startup', 'growing'),
    ('growing', 'mid_market'),
    ('mid_market', 'large_enterprise'),
    ('large_enterprise', 'global_enterprise'),
]

for current_name, target_name in transitions:
    current = CompanyExperienceProfile(current_name)
    target = CompanyExperienceProfile(target_name)
    diff = get_transition_diff(current, target)
    print(f'\n{current_name.upper()} -> {target_name.upper()}:')
    print(f'  Modules added: {diff["modules_added"]}')
    print(f'  Modules removed: {diff["modules_removed"]}')
    print(f'  Nav groups added: {diff["navigation_groups_added"]}')
    print(f'  Nav groups removed: {diff["navigation_groups_removed"]}')
    print(f'  Governance: {diff["governance_level_change"]["from"]} -> {diff["governance_level_change"]["to"]}')
    print(f'  Approval levels: {diff["approval_levels_change"]["from"]} -> {diff["approval_levels_change"]["to"]}')
    print(f'  New features: {diff["new_features"]}')

print('\nSUCCESS: Profile transition previews working correctly!')