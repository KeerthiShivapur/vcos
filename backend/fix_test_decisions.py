with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix the test to check company_decisions instead of decisions
old = '''        # The decisions component should show the change
        dec_comp_1 = next((c for c in fp1.components if c.component_name == "decisions"), None)
        dec_comp_2 = next((c for c in fp2.components if c.component_name == "decisions"), None)
        assert dec_comp_1 is not None and dec_comp_2 is not None
        assert dec_comp_1.fingerprint != dec_comp_2.fingerprint
        assert dec_comp_2.entity_count > dec_comp_1.entity_count'''

new = '''        # The company_decisions component should show the change
        dec_comp_1 = next((c for c in fp1.components if c.component_name == "company_decisions"), None)
        dec_comp_2 = next((c for c in fp2.components if c.component_name == "company_decisions"), None)
        assert dec_comp_1 is not None and dec_comp_2 is not None
        assert dec_comp_1.fingerprint != dec_comp_2.fingerprint
        assert dec_comp_2.entity_count > dec_comp_1.entity_count'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')