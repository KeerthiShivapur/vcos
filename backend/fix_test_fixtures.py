with open('tests/acceptance/test_real_company_onboarding.py', 'r') as f:
    content = f.read()

# Add clean_provisionings to all test methods
import re

# Pattern to match test method signatures without clean_provisionings
pattern = r'(async def test_\w+\(\s*self,\s*pg_db_session: AsyncSession,\s*onboarding_context: OnboardingContext,\s*\):)'

def add_fixture(match):
    sig = match.group(1)
    # Add clean_provisionings fixture
    new_sig = sig.replace(
        'onboarding_context: OnboardingContext,',
        'onboarding_context: OnboardingContext,\n        clean_provisionings: None,'
    )
    return new_sig

content = re.sub(pattern, add_fixture, content)

# Also fix the two tests that don't have onboarding_context fixture
# test_onboarding_handles_domain_conflict and test_onboarding_handles_email_conflict

# Fix test_onboarding_handles_domain_conflict
old_domain = '''    @pytest.mark.asyncio
    async def test_onboarding_handles_domain_conflict(
        self,
        pg_db_session: AsyncSession,
    ):'''

new_domain = '''    @pytest.mark.asyncio
    async def test_onboarding_handles_domain_conflict(
        self,
        pg_db_session: AsyncSession,
        clean_provisionings: None,
    ):'''

content = content.replace(old_domain, new_domain)

# Fix test_onboarding_handles_email_conflict
old_email = '''    @pytest.mark.asyncio
    async def test_onboarding_handles_email_conflict(
        self,
        pg_db_session: AsyncSession,
    ):'''

new_email = '''    @pytest.mark.asyncio
    async def test_onboarding_handles_email_conflict(
        self,
        pg_db_session: AsyncSession,
        clean_provisionings: None,
    ):'''

content = content.replace(old_email, new_email)

with open('tests/acceptance/test_real_company_onboarding.py', 'w') as f:
    f.write(content)
print('Done')