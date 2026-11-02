with open('tests/acceptance/test_release_candidate_slice_2a.py', 'r') as f:
    content = f.read()

# Add unique suffix to organization slugs to avoid conflicts
import re

# Fix the slug in test_all_prerequisites_pass_ready
old = '''# Create a minimal valid organization
        org = Organization(
            name="Test Org",
            slug="test-org-2a",
            status="active",
        )'''

new = '''# Create a minimal valid organization
        import uuid
        org = Organization(
            name="Test Org",
            slug=f"test-org-2a-{uuid.uuid4().hex[:8]}",
            status="active",
        )'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2a.py', 'w') as f:
    f.write(content)
print('Done')