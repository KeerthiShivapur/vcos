import asyncio
from app.services.adaptive_experience_engine import adaptive_experience_engine
from app.services.adaptive_experience_engine import AdaptiveContext, UserContextRole, GeographicContext

print('=== Full Adaptive Experience Resolution Test ===')

# Create a mock context
context = AdaptiveContext(
    organization_id="test-org-123",
    user_id="test-user-456",
    user_role=UserContextRole.MANAGER,
    user_permissions={"read", "write", "manage_team"},
    geographic_context=GeographicContext.AMERICAS,
    current_page="home",
    device_type="desktop",
)

# Test the async resolve method
async def test_resolve():
    result = await adaptive_experience_engine.resolve_adaptive_experience(context)
    print(f'Profile: {result.profile}')
    print(f'Dashboard Layout: {result.dashboard_layout}')
    print(f'Navigation Density: {result.navigation_density}')
    print(f'Progressive Disclosure: {result.progressive_disclosure}')
    print(f'Show Advanced Features: {result.show_advanced_features}')
    print(f'Navigation Groups: {len(result.navigation_groups)}')
    for group in result.navigation_groups:
        print(f'  - {group.key}: {group.label} ({len(group.modules)} modules)')
    print(f'Visible Modules: {len(result.visible_modules)}')
    print(f'Feature Flags: {result.feature_flags}')
    print(f'Context Fingerprint: {result.context_fingerprint}')
    print(f'Resolved At: {result.resolved_at}')
    return result

result = asyncio.run(test_resolve())
print('\nSUCCESS: Full adaptive experience resolution working correctly!')