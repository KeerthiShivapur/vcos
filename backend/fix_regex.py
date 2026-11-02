with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the problematic section
idx = content.find('logger.info("')
if content.find('Incomplete restore correctly rejected') >= 0:
    # Find the exact problematic section
    start = content.find('logger.info("')
    while content.find('logger.info("', start) >= 0:
        start = content.find('logger.info("', start)
        if start >= 0:
            end = content.find('\n', start)
            if end >= 0:
                line = content[start:end+1]
                if 'Incomplete restore' in line:
                    print(f'Found at {start}: {repr(line)}')
                    break
        start = content.find('logger.info("', start + 1)

# Write a fixed version
with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all problematic lines
import re
# Remove any logger.info lines with checkmark emoji for this test
content = re.sub(r'logger\.info\(".*?Incomplete restore correctly rejected on real PostgreSQL.*?\)\s*assert.*?\n', '', content)
content = re.sub(r'logger\.info\(".*?Incomplete restore correctly rejected on real PostgreSQL.*?\)\s*\n', '', content)

# Add proper logger.info line
# Find the incomplete restore test and fix it
old_pattern = r'(        assert "not found" in result\["error"\]\.lower\(\) or "backup" in result\["error"\]\.lower\(\)\n\s*\n\s*logger\.info\(.*?Incomplete restore.*?\)\s*assert.*?\n\s*logger\.info\(.*?Incomplete restore.*?\)\s*\n\s*@pytest\.mark\.asyncio)'
new_text = '''        assert "not found" in result["error"].lower() or "backup" in result["error"].lower()
        
        logger.info("Incomplete restore correctly rejected on real PostgreSQL")
        
    @pytest.mark.asyncio'''

content = re.sub(old_pattern, new_text, content, flags=re.DOTALL)

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed with regex")