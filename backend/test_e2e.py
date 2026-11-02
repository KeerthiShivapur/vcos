import asyncio
from app.db.database import init_db, SessionLocal
from app.services.adaptive_experience_engine import adaptive_experience_engine, AdaptiveContext, UserContextRole, GeographicContext
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from sqlalchemy import select

async def test_full_flow():
    await init_db()
    async with SessionLocal() as db:
        # Get first org
        result = await db.execute(select(Organization).limit(1))
        org = result.scalar_one_or_none()
        if not org:
            print('No organizations found')
            return
        
        # Get first user in org
        result = await db.execute(select(User).where(User.organization_id == org.id).limit(1))
        user = result.scalar_one_or_none()
        
        # Get employee record for role mapping
        employee = None
        if user:
            result = await db.execute(select(Employee).where(Employee.user_id == user.id, Employee.organization_id == org.id))
            employee = result.scalar_one_or_none()
        
        print(f'Org: {org.id} - {org.name}')
        print(f'User: {user.id if user else "None"} - {user.email if user else "None"}')
        print(f'Employee: {employee.id if employee else "None"} - {employee.designation if employee else "None"}')
        print(f'User Role: {user.role if user else "None"}')
        print(f'User Permissions: {user.permissions if user else "None"}')
        
        # Map user role to context role
        role_mapping = {
            "ceo": UserContextRole.EXECUTIVE,
            "admin": UserContextRole.ADMIN,
            "manager": UserContextRole.MANAGER,
            "hr": UserContextRole.HR,
            "finance": UserContextRole.FINANCE,
            "developer": UserContextRole.DEVELOPER,
            "employee": UserContextRole.EMPLOYEE,
        }
        user_context_role = role_mapping.get(user.role if user else "employee", UserContextRole.EMPLOYEE)
        if employee and employee.designation:
            if "manager" in employee.designation.lower() or "lead" in employee.designation.lower():
                user_context_role = UserContextRole.MANAGER
            elif "executive" in employee.designation.lower() or "director" in employee.designation.lower() or "vp" in employee.designation.lower():
                user_context_role = UserContextRole.EXECUTIVE
        
        print(f'Context Role: {user_context_role.value}')
        
        # Create context
        context = AdaptiveContext(
            organization_id=org.id,
            user_id=user.id if user else 'test-user',
            user_role=user_context_role,
            user_permissions=set(user.permissions or []) if user else set(),
            geographic_context=GeographicContext.GLOBAL,
        )
        
        # Resolve adaptive experience
        config = await adaptive_experience_engine.resolve_adaptive_experience(db, context)
        print(f'\n=== ADAPTIVE EXPERIENCE ===')
        print(f'Profile: {config.profile.value}')
        print(f'Dashboard Layout: {config.dashboard_layout}')
        print(f'Navigation Density: {config.navigation_density}')
        print(f'Progressive Disclosure: {config.progressive_disclosure}')
        print(f'Show Advanced: {config.show_advanced_features}')
        print(f'Feature Flags: {config.feature_flags}')
        
        print(f'\n=== NAVIGATION GROUPS ({len(config.navigation_groups)}) ===')
        for g in config.navigation_groups:
            print(f'  {g.key}: {g.label} (priority={g.priority}, collapsed={g.default_collapsed})')
            for m in g.modules:
                print(f'    - {m.key}: {m.label} (priority={m.priority}, perm={m.required_permissions})')
        
        print(f'\n=== VISIBLE MODULES ({len(config.visible_modules)}) ===')
        for m in config.visible_modules:
            print(f'  - {m}')
        
        print(f'\n=== COMPANY BRAIN INSIGHTS ===')
        print(f'  Overview: {config.company_brain_insights.get("overview", {})}')
        print(f'  Recent Changes: {len(config.company_brain_insights.get("recent_changes", []))}')
        print(f'  Change Count: {config.company_brain_insights.get("change_count", 0)}')
        
        print(f'\n=== DIGITAL TWIN OVERLAY ===')
        print(f'  Health Score: {config.digital_twin_overlay.get("health_score", 0)}')
        print(f'  Capacity Utilization: {config.digital_twin_overlay.get("capacity_utilization", 0)}')
        print(f'  Bottlenecks: {config.digital_twin_overlay.get("bottlenecks", [])}')
        print(f'  Active Scenarios: {config.digital_twin_overlay.get("active_scenarios", 0)}')
        
        print(f'\n=== RECOMMENDED ACTIONS ({len(config.recommended_actions)}) ===')
        for a in config.recommended_actions:
            print(f'  - {a["type"]}: {a["label"]} -> {a["target"]} (priority={a["priority"]})')
        
        print(f'\n=== CONTEXT FINGERPRINT ===')
        print(f'  {config.context_fingerprint}')
        
        # Test module recommendations
        print(f'\n=== MODULE RECOMMENDATIONS ===')
        recommendations = await adaptive_experience_engine.get_module_recommendations(db, context, 5)
        for m in recommendations:
            print(f'  - {m.key}: {m.label} (priority={m.priority})')
        
        # Test profile transition preview
        print(f'\n=== PROFILE TRANSITION PREVIEW ===')
        from app.models.company_experience import CompanyExperienceProfile
        for target in [CompanyExperienceProfile.GROWING, CompanyExperienceProfile.MID_MARKET, CompanyExperienceProfile.LARGE_ENTERPRISE]:
            preview = await adaptive_experience_engine.get_profile_transition_preview(db, org.id, target)
            print(f'  To {target.value}:')
            print(f'    Modules added: {preview["modules_added"]}')
            print(f'    Nav groups added: {preview["navigation_groups_added"]}')
            print(f'    Governance: {preview["governance_level_change"]}')
            print(f'    Approval levels: {preview["approval_levels_change"]}')
        
        print('\n=== ALL TESTS PASSED ===')

asyncio.run(test_full_flow())