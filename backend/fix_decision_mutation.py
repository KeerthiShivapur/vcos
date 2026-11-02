import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and fix the decision creation to use the mutation function pattern
old_block = '''        # Create a decision through canonical mutation
        decision = CompanyDecision(
            organization_id=org.id,
            title="Adopt Microservices Architecture",
            kind="strategic",
            rationale="Adopt microservices for platform modernization",
            state="approved",
            outcome_kind="approved",
            approved_at=utcnow(),
            approver_label=access.employee_id,
            source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
            epistemic_status=EpistemicStatus.EVIDENCE_BACKED,
        )
        
        decision_result = await canonical_mutation_boundary.mutate(
            db_session,
            access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            entity=decision,
        )'''

new_block = '''        # Create a decision through canonical mutation
        decision = CompanyDecision(
            organization_id=org.id,
            title="Adopt Microservices Architecture",
            kind="strategic",
            rationale="Adopt microservices for platform modernization",
            state="proposed",
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
        )
        
        async def create_decision_fn(db):
            db.add(decision)
            await db.flush()
            return decision
        
        decision_result = await canonical_mutation_boundary.mutate(
            db=db_session,
            caller=access,
            target_entity_type="CompanyDecision",
            mutation_type=MutationType.CREATE,
            mutation_fn=create_decision_fn,
        )'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed decision creation')
else:
    print('Block not found')