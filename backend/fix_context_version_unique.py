import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the build_universal_context call and add context_version
old_call = '''        rebuilt_context = await canonical_company_continuity_service.build_universal_context(
            db=db_session,
            organization_id=org.id,
            caller_user_id=str(admin_user.id),
        )'''

new_call = '''        # Use unique context_version to avoid UNIQUE constraint conflicts with other test data
        import time
        unique_context_version = int(time.time() * 1000) % 1000000
        
        rebuilt_context = await canonical_company_continuity_service.build_universal_context(
            db=db_session,
            organization_id=org.id,
            caller_user_id=str(admin_user.id),
            context_version=unique_context_version,
        )'''

if old_call in content:
    content = content.replace(old_call, new_call)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added unique context_version to build_universal_context call')
else:
    print('Pattern not found')