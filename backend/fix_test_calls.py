with open('tests/acceptance/test_real_company_onboarding.py', 'r') as f:
    content = f.read()

# Fix test methods that have clean_provisionings fixture
import re

# Fix test_onboarding_context_tracks_phases
old = '''    async def test_onboarding_context_tracks_phases(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
        clean_provisionings: None,
    ):'''

new = '''    async def test_onboarding_context_tracks_phases(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)'''

content = content.replace(old, new)

# Fix test_provisioning_completes_all_steps
old = '''    async def test_provisioning_completes_all_steps(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
        clean_provisionings: None,
    ):'''

new = '''    async def test_provisioning_completes_all_steps(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)'''

content = content.replace(old, new)

# Fix test_invite_initial_employees
old = '''    async def test_invite_initial_employees(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
        clean_provisionings: None,
    ):'''

new = '''    async def test_invite_initial_employees(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)'''

content = content.replace(old, new)

# Fix test_workspace_setup
old = '''    async def test_workspace_setup(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
        clean_provisionings: None,
    ):'''

new = '''    async def test_workspace_setup(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)'''

content = content.replace(old, new)

# Fix test_canonical_reality_initialization
old = '''    async def test_canonical_reality_initialization(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
        clean_provisionings: None,
    ):'''

new = '''    async def test_canonical_reality_initialization(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)'''

content = content.replace(old, new)

# Fix test_onboarding_progress_tracking
old = '''    async def test_onboarding_progress_tracking(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
        clean_provisionings: None,
    ):'''

new = '''    async def test_onboarding_progress_tracking(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        await _clean_provisionings(pg_db_session)'''

content = content.replace(old, new)

# Fix test_onboarding_handles_domain_conflict
old = '''    async def test_onboarding_handles_domain_conflict(
        self,
        pg_db_session: AsyncSession,
        clean_provisionings: None,
    ):'''

new = '''    async def test_onboarding_handles_domain_conflict(
        self,
        pg_db_session: AsyncSession,
        clean_provisionings: None,
    ):
        await _clean_provisionings(pg_db_session)'''

content = content.replace(old, new)

# Fix test_onboarding_handles_email_conflict
old = '''    async def test_onboarding_handles_email_conflict(
        self,
        pg_db_session: AsyncSession,
        clean_provisionings: None,
    ):'''

new = '''    async def test_onboarding_handles_email_conflict(
        self,
        pg_db_session: AsyncSession,
        clean_provisionings: None,
    ):
        await _clean_provisionings(pg_db_session)'''

content = content.replace(old, new)

with open('tests/acceptance/test_real_company_onboarding.py', 'w') as f:
    f.write(content)
print('Done')