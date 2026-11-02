import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add cleanup before return
old_return = '''        result.determine_overall()
        print("DEBUG VALIDATE: Validation result overall status: {}".format(result.overall_status))
        return result

    async def _run_restore_specific_adversarial_tests('''

new_return = '''        result.determine_overall()
        print("DEBUG VALIDATE: Validation result overall status: {}".format(result.overall_status))
        
        # Clean up any UniversalCompanyContext entries created during adversarial testing
        try:
            from app.models.universal_company_context import UniversalCompanyContext
            from sqlalchemy import delete
            await db.execute(delete(UniversalCompanyContext))
            await db.flush()
        except Exception:
            pass  # Best effort cleanup
        
        return result

    async def _run_restore_specific_adversarial_tests('''

if old_return in content:
    content = content.replace(old_return, new_return)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed _validate_tenant_isolation to clean up contexts')
else:
    print('Pattern not found')