import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging at the start of the test function
old_func = '''    async def test_complete_production_dr_lifecycle(self, db_session, production_company):
        """
        Complete Production Deployment + DR E2E lifecycle.

        PROVISION \u2192 OPERATE \u2192 BUILD MEMORY \u2192 ASK COMPANY \u2192 SIMULATE \u2192 GOVERN 
        \u2192 CONTINUITY \u2192 BACKUP \u2192 DISASTER \u2192 RESTORE \u2192 VALIDATE \u2192 REBUILD 
        \u2192 ASK AGAIN \u2192 SIMULATE AGAIN \u2192 GOVERN AGAIN \u2192 CONTINUE OPERATING
        """
        
        global uuid
        org = production_company["organization"]'''

new_func = '''    async def test_complete_production_dr_lifecycle(self, db_session, production_company):
        """
        Complete Production Deployment + DR E2E lifecycle.

        PROVISION \u2192 OPERATE \u2192 BUILD MEMORY \u2192 ASK COMPANY \u2192 SIMULATE \u2192 GOVERN 
        \u2192 CONTINUITY \u2192 BACKUP \u2192 DISASTER \u2192 RESTORE \u2192 VALIDATE \u2192 REBUILD 
        \u2192 ASK AGAIN \u2192 SIMULATE AGAIN \u2192 GOVERN AGAIN \u2192 CONTINUE OPERATING
        """
        
        global uuid
        logger.info("=== Starting test_complete_production_dr_lifecycle ===")
        org = production_company["organization"]'''

if old in content:
    content = content.replace(old_func, new_func)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging at start')
else:
    print('Pattern not found')