with open('tests/test_gate6g_exact_once_concurrency.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the CompanyAuthorization creation in test_concurrent_transition_race
content = content.replace(
    '''auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            id="auth-race-" + uuid.uuid4().hex[:8],
            decision_id="dec-race-" + uuid.uuid4().hex[:8],
            policy_id="pol-race-" + uuid.uuid4().hex[:8],
            title="Race Auth",
            state="requested",
            source_event_id="evt-race",''',
    '''auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            id="auth-race-" + uuid.uuid4().hex[:8],
            decision_id="dec-race-" + uuid.uuid4().hex[:8],
            policy_id="pol-race-" + uuid.uuid4().hex[:8],
            title="Race Auth",
            state="requested",
            source_event_id="evt-race",
            fingerprint="fp-race-" + uuid.uuid4().hex[:8],''')

# Fix the other CompanyAuthorization creation
content = content.replace(
    '''auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            id="auth-concurrency-" + uuid.uuid4().hex[:8],
            decision_id="dec-concurrency-" + uuid.uuid4().hex[:8],
            policy_id="pol-concurrency-" + uuid.uuid4().hex[:8],
            title="Concurrency Auth",
            state="requested",
            source_event_id="evt-concurrency",''',
    '''auth = CompanyAuthorization(
            organization_id=test_org_a.id,
            id="auth-concurrency-" + uuid.uuid4().hex[:8],
            decision_id="dec-concurrency-" + uuid.uuid4().hex[:8],
            policy_id="pol-concurrency-" + uuid.uuid4().hex[:8],
            title="Concurrency Auth",
            state="requested",
            source_event_id="evt-concurrency",
            fingerprint="fp-concurrency-" + uuid.uuid4().hex[:8],''')

with open('tests/test_gate6g_exact_once_concurrency.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed CompanyAuthorization fingerprint fields')