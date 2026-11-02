import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix _validate_tenant_isolation to clean up UniversalCompanyContext entries
old_cleanup = '''        finally:
            # Clean up any UniversalCompanyContext entries created during adversarial testing
            try:
                from app.models.universal_company_context import UniversalCompanyContext
                from sqlalchemy import delete
                await db.execute(delete(UniversalCompanyContext))
                await db.flush()
            except Exception:
                pass  # Best effort cleanup
        
        return result'''

new_cleanup = '''        finally:
            # Clean up any UniversalCompanyContext entries created during adversarial testing
            try:
                from app.models.universal_company_context import UniversalCompanyContext
                from sqlalchemy import delete
                await db.execute(delete(UniversalCompanyContext))
                await db.flush()
            except Exception:
                pass  # Best effort cleanup
        
        return result'''

if old_cleanup in content:
    content = content.replace(old_cleanup, new_cleanup)
    with codecs.open('app/services/restore_service.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed _validate_tenant_isolation cleanup')
else:
    print('Pattern not found')