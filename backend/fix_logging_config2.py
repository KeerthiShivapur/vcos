import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add logging configuration after imports
old = '''import pytest
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession'''

new = '''import pytest
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

# Configure logging for test
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")'''

if old in content:
    content = content.replace(old, new)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added logging configuration')
else:
    print('Pattern not found')