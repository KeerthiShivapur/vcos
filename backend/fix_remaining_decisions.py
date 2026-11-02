import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix first CompanyDecision (Adopt Microservices Architecture)
old1 = '''        # Create a decision through canonical mutation
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

new1 = '''        # Create a decision through canonical mutation
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

# Fix second CompanyDecision (Post-Restore Strategic Decision)
old2 = '''        new_decision = CompanyDecision(
            organization_id=org.id,
            title="Post-Restore Strategic Decision",
            kind="operational",
            description="Verify company can make new decisions after restore",
            state="proposed",
            outcome_kind="pending",
            decision_date=utcnow(),
            decided_by=access.employee_id,
            source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.PROPOSED,
        )'''

new2 = '''        new_decision = CompanyDecision(
            organization_id=org.id,
            title="Post-Restore Strategic Decision",
            kind="operational",
            rationale="Verify company can make new decisions after restore",
            state="proposed",
            outcome_kind="pending",
            approved_at=utcnow(),
            decided_by=access.employee_id,
            source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.PROPOSED,
        )'''

replacements = [
    (old1, new1),
    (old2, new2),
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f'Fixed one block')
    else:
        print(f'Block not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')