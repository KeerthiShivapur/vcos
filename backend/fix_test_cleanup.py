import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add cleanup at the start of the test
old_test_start = '''    @pytest.mark.asyncio
    async def test_complete_production_dr_lifecycle(self, db_session, production_company):
        """
        Complete Production Deployment + DR E2E lifecycle.
    
        PROVISION \u2192 OPERATE \u2192 BUILD MEMORY \u2192 ASK COMPANY \u2192 SIMULATE \u2192 GOVERN 
        \u2192 CONTINUITY \u2192 BACKUP \u2192 DISASTER \u2192 RESTORE \u2192 VALIDATE \u2192 REBUILD 
        \u2192 ASK AGAIN \u2192 SIMULATE AGAIN \u2192 GOVERN AGAIN \u2192 CONTINUE OPERATING
        """
        
        org = production_company["organization"]
        admin_user = production_company["admin_user"]
        access = production_company["access"]'''

new_test_start = '''    @pytest.mark.asyncio
    async def test_complete_production_dr_lifecycle(self, db_session, production_company):
        """
        Complete Production Deployment + DR E2E lifecycle.
    
        PROVISION \u2192 OPERATE \u2192 BUILD MEMORY \u2192 ASK COMPANY \u2192 SIMULATE \u2192 GOVERN 
        \u2192 CONTINUITY \u2192 BACKUP \u2192 DISASTER \u2192 RESTORE \u2192 VALIDATE \u2192 REBUILD 
        \u2192 ASK AGAIN \u2192 SIMULATE AGAIN \u2192 GOVERN AGAIN \u2192 CONTINUE OPERATING
        """
        
        # Clean up any leftover UniversalCompanyContext entries from previous test runs
        from app.models.universal_company_context import UniversalCompanyContext
        from sqlalchemy import delete
        await db_session.execute(delete(UniversalCompanyContext))
        await db_session.flush()
        
        org = production_company["organization"]
        admin_user = production_company["admin_user"]
        access = production_company["access"]'''

if old_test_start in content:
    content = content.replace(old_test_start, new_test_start)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added cleanup at test start')
else:
    print('Pattern not found')