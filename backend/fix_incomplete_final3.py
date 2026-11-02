with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_text = '        assert "not found" in result["error"].lower() or "backup" in result["error"].lower()\n        \n\n    @pytest.mark.asyncio'

new_text = '''        assert "not found" in result["error"].lower() or "backup" in result["error"].lower()
        
        logger.info("✅ Incomplete restore correctly rejected on real PostgreSQL")
        
    @pytest.mark.asyncio'''

content = content.replace(old_text, new_text)

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed")