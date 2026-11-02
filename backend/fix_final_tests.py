with open('tests/test_gate23_canonical_business_intelligence.py', 'r') as f:
    content = f.read()

# Fix 1: test_exact_once_bi_context - Use proper IntegrityError handling
content = content.replace(
    '''async def test_exact_once_bi_context(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test exact-once constraint on BI contexts."""
        # The exact-once constraint is enforced at the database level via unique constraint
        # on (organization_id, context_type, context_entity_id, period_label, source_event_id)
        # We verify the constraint exists rather than attempting to create duplicates
        from sqlalchemy import inspect
        async with db_session.bind.connect() as conn:
            def check_constraints(sync_conn):
                inspector = inspect(sync_conn)
                indexes = inspector.get_indexes('business_intelligence_contexts')
                unique_indexes = [idx for idx in indexes if idx.get('unique')]
                has_exact_once_constraint = any(
                    set(['organization_id', 'context_type', 'context_entity_id', 'period_label', 'source_event_id']).issubset(set(idx['column_names']))
                    for idx in unique_indexes if idx.get('unique')
                )
                return has_exact_once_constraint
            has_exact_once_constraint = await conn.run_sync(check_constraints)
        assert has_exact_once_constraint, "Exact-once unique constraint not found on business_intelligence_contexts"''',
    '''async def test_exact_once_bi_context(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test exact-once constraint on BI contexts."""
        # The exact-once constraint is enforced at the database level via unique constraint
        # on (organization_id, context_type, context_entity_id, period_label, source_event_id)
        # We verify the constraint by attempting to create a duplicate and expecting a constraint violation
        from sqlalchemy.exc import IntegrityError
        
        event_id = f"bi_ctx_exact_once:{uuid.uuid4().hex[:8]}"
        
        # Create first context
        ctx1 = await canonical_business_intelligence_service.derive_bi_context(
            db_session, caller=test_caller, context_type="company", context_entity_id="org", period_label="2026-01"
        )
        # Manually set the source_event_id to test exact-once
        ctx1.source_event_id = event_id
        await db_session.flush()
        
        # Try to create another context with the same source_event_id - should fail
        ctx2 = await canonical_business_intelligence_service.derive_bi_context(
            db_session, caller=test_caller, context_type="company", context_entity_id="org", period_label="2026-01"
        )
        ctx2.source_event_id = event_id
        
        try:
            await db_session.flush()
            assert False, "Expected IntegrityError for duplicate source_event_id"
        except IntegrityError:
            pass  # Expected - unique constraint violation
        
        # Verify only one record exists with that source_event_id
        ctx_count = await db_session.execute(
            __import__('sqlalchemy').select(__import__('sqlalchemy').func.count(BusinessIntelligenceContext.id)).where(
                BusinessIntelligenceContext.organization_id == test_caller.organization_id,
                BusinessIntelligenceContext.context_type == "company",
                BusinessIntelligenceContext.context_entity_id == "org",
                BusinessIntelligenceContext.period_label == "2026-01",
                BusinessIntelligenceContext.source_event_id == event_id,
            )
        )
        assert ctx_count.scalar_one() == 1''',
)

# Fix 2: test_strategy_to_execution_to_learning_loop - CompanyCommitment fingerprint NOT NULL
content = content.replace(
    '''# 4. Commitment for initiative
          commitment = CompanyCommitment(
              id=f"comm-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Close 5 Enterprise Deals",
              commitment_type="delivery",
              scope_type="initiative",
              scope_id=initiative.id,
              objective_id=objective.id,
              state="active",
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:200]}",
              version=1,
          )''',
    '''# 4. Commitment for initiative
          commitment = CompanyCommitment(
              id=f"comm-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Close 5 Enterprise Deals",
              commitment_type="delivery",
              scope_type="initiative",
              scope_id=initiative.id,
              objective_id=objective.id,
              state="active",
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:240]}",
              version=1,
          )''',
)

# Fix 3: test_company_decision_still_works - CompanyDecision.decision_id NOT NULL
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 3b: second CompanyDecision in regression test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 4: test_same_architecture_small_company - employees.email NOT NULL
content = content.replace(
    '''        for i in range(5):
            emp = Employee(
                id=f"emp-small-{i}-{uuid.uuid4().hex[:8]}",
                organization_id=test_caller.organization_id,
                employee_number=f"E00{i}",
                first_name=f"Employee",
                last_name=f"{i}",
                display_name=f"Employee {i}",
                status="active",
            )''',
    '''        for i in range(5):
            emp = Employee(
                id=f"emp-small-{i}-{uuid.uuid4().hex[:8]}",
                organization_id=test_caller.organization_id,
                employee_number=f"E00{i}",
                first_name=f"Employee",
                last_name=f"{i}",
                display_name=f"Employee {i}",
                email=f"employee{i}@test.com",
                status="active",
            )''',
)

# Fix 5: test_decision_not_authorization_not_commitment - CompanyDecision.decision_id NOT NULL
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 5b: second CompanyDecision in architectural test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 5c: CompanyDecision for end-to-end test (strategy_to_execution)
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 5d: second CompanyDecision in end-to-end test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 6: test_strategy_to_execution_to_learning_loop - CompanyCommitment fingerprint NOT NULL
content = content.replace(
    '''# 4. Commitment for initiative
          commitment = CompanyCommitment(
              id=f"comm-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Close 5 Enterprise Deals",
              commitment_type="delivery",
              scope_type="initiative",
              scope_id=initiative.id,
              objective_id=objective.id,
              state="active",
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:200]}",
              version=1,
          )''',
    '''# 4. Commitment for initiative
          commitment = CompanyCommitment(
              id=f"comm-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Close 5 Enterprise Deals",
              commitment_type="delivery",
              scope_type="initiative",
              scope_id=initiative.id,
              objective_id=objective.id,
              state="active",
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:240]}",
              version=1,
          )''',
)

# Fix 7: test_same_architecture_small_company - employees.email NOT NULL
content = content.replace(
    '''        for i in range(5):
            emp = Employee(
                id=f"emp-small-{i}-{uuid.uuid4().hex[:8]}",
                organization_id=test_caller.organization_id,
                employee_number=f"E00{i}",
                first_name=f"Employee",
                last_name=f"{i}",
                display_name=f"Employee {i}",
                status="active",
            )''',
    '''        for i in range(5):
            emp = Employee(
                id=f"emp-small-{i}-{uuid.uuid4().hex[:8]}",
                organization_id=test_caller.organization_id,
                employee_number=f"E00{i}",
                first_name=f"Employee",
                last_name=f"{i}",
                display_name=f"Employee {i}",
                email=f"employee{i}@test.com",
                status="active",
            )''',
)

# Fix 5c: CompanyDecision for end-to-end test (strategy_to_execution)
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 5d: second CompanyDecision in end-to-end test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 5c: CompanyDecision for architectural test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
)

# Fix 5d: second CompanyDecision in architectural test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              decision_id=f"dec-{uuid.uuid4().hex[:8]}",
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )''',
)

with open('tests/test_gate23_canonical_business_intelligence.py', 'w') as f:
    f.write(content)

print('Fixed all test issues')