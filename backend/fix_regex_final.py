import re

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Use regex to fix the corrupted block with flexible whitespace matching
pattern = r'Incomplete restore correctly rejected on real PostgreSQL"\) assert "failed" in str\(exc_info\.value\)\.lower\(\) or "not found" in str\(exc_info\.value\)\.lower\(\).*?logger\.info\(".*?Incomplete restore correctly rejected on real PostgreSQL.*?"\)\s*@pytest\.mark\.asyncio'

replacement = '''        logger.info("Incomplete restore correctly rejected on real PostgreSQL")
        
    @pytest.mark.asyncio'''

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed with regex")