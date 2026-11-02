import codecs
import re

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the CompanyDecision creation in multi-tenant test
old_block = '''            dec = CompanyDecision(
                organization_id=org.id,
                title=f"Org {i+1} Decision",
                kind="strategic",
                state="approved",
                approved_at=utcnow(),
                decided_by=access.employee_id,
                source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
                epistemic_status=EpistemicStatus.EVIDENCE_BACKED,
            )'''

new_block = '''            dec = CompanyDecision(
                organization_id=org.id,
                title=f"Org {i+1} Decision",
                kind="strategic",
                state="approved",
                rationale="Test decision for multi-tenant DR",
                approved_at=utcnow(),
                decided_by=access.employee_id,
                source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
                epistemic_status=EpistemicStatus.EVIDENCE_BACKED,
            )'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed CompanyDecision creation in multi-tenant test')
else:
    print('Block not found')

# Also fix the CompanyDecision creation in main test (decision for commit)
old_block2 = '''        # Create a decision through canonical mutation
        decision = CompanyDecision(
            organization_id=org.id,
            title="Adopt Microservices Architecture",
            kind="strategic",
            description="Adopt microservices for platform modernization",
            state="approved",
            outcome_kind="approved",
            decision_date=utcnow(),
            decided_by=access.employee_id,
            source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.CONFIRMED,
        )'''

new_block2 = '''        # Create a decision through canonical mutation
        decision = CompanyDecision(
            organization_id=org.id,
            title="Adopt Microservices Architecture",
            kind="strategic",
            rationale="Adopt microservices for platform modernization",
            state="approved",
            outcome_kind="approved",
            approved_at=utcnow(),
            decided_by=access.employee_id,
            source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.EVIDENCE_BACKED,
        )'''

if old_block2 in content:
    content = content.replace(old_block2, new_block2)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed CompanyDecision creation in main test')
else:
    print('Main test block not found')