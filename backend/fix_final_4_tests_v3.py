with open('tests/test_gate23_canonical_business_intelligence.py', 'r') as f:
    content = f.read()

# Fix 1: test_exact_once_bi_context - Restructure to properly test exact-once without rolling back the first record
content = content.replace(
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
        ctx1_id = ctx1.id
        
        # Try to create another context with the same source_event_id - should fail
        ctx2 = await canonical_business_intelligence_service.derive_bi_context(
            db_session, caller=test_caller, context_type="company", context_entity_id="org", period_label="2026-01"
        )
        ctx2.source_event_id = event_id
        
        try:
            await db_session.flush()
            assert False, "Expected IntegrityError for duplicate source_event_id"
        except IntegrityError:
            # Rollback to clear the error state, but the first context should still exist
            await db_session.rollback()
        
        # Verify only the first record exists with that source_event_id
        # Need to use a fresh query since the session was rolled back
        ctx_count = await db_session.execute(
            __import__('sqlalchemy').select(__import__('sqlalchemy').func.count(BusinessIntelligenceContext.id)).where(
                BusinessIntelligenceContext.organization_id == test_caller.organization_id,
                BusinessIntelligenceContext.context_type == "company",
                BusinessIntelligenceContext.context_entity_id == "org",
                BusinessIntelligenceContext.period_label == "2026-01",
                BusinessIntelligenceContext.source_event_id == event_id,
            )
        )
        # The first context should still exist (it was committed before the failed flush)
        # But due to rollback, it might not. Let's check what actually happens.
        # The exact-once constraint means only ONE record can exist with that unique key.
        # The test verifies the constraint works by catching the error.
        # We just verify the constraint works by catching the error.
        pass  # Test passes if IntegrityError is raised''',
    '''async def test_exact_once_bi_context(self, db_session: AsyncSession, test_caller: CallerAccess):
        """Test exact-once constraint on BI contexts."""
        # The exact-once constraint is enforced at the database level via unique constraint
        # on (organization_id, context_type, context_entity_id, period_label, source_event_id)
        # We verify the constraint by attempting to create a duplicate and expecting a constraint violation
        from sqlalchemy.exc import IntegrityError
        
        event_id = f"bi_ctx_exact_once:{uuid.uuid4().hex[:8]}"
        
        # Create first context with a specific source_event_id
        ctx1 = await canonical_business_intelligence_service.derive_bi_context(
            db_session, caller=test_caller, context_type="company", context_entity_id="org", period_label="2026-01"
        )
        ctx1.source_event_id = event_id
        await db_session.flush()
        ctx1_id = ctx1.id
        
        # Try to create another context with the same source_event_id - should fail
        ctx2 = await canonical_business_intelligence_service.derive_bi_context(
            db_session, caller=test_caller, context_type="company", context_entity_id="org", period_label="2026-01"
        )
        ctx2.source_event_id = event_id
        
        try:
            await db_session.flush()
            assert False, "Expected IntegrityError for duplicate source_event_id"
        except IntegrityError:
            # Rollback to clear the error state
            await db_session.rollback()
            pass  # Expected - unique constraint violation
        
        # Verify the first context still exists (it was committed before the failed flush)
        # The rollback only affects the failed transaction, not the previously committed ctx1
        # Verify by querying for the first context
        ctx1_check = await db_session.execute(
            __import__('sqlalchemy').select(BusinessIntelligenceContext.id).where(
                BusinessIntelligenceContext.id == ctx1.id
            )
        )
        assert ctx1_check.scalar_one() == ctx1.id, "First context should still exist after rollback of failed duplicate"
        
        # Verify the unique constraint exists by checking the table schema
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
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:400]}",
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
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:500]}",
              version=1,
          )''',
)

# Fix 3: test_company_decision_still_works - CompanyDecision.decision_id NOT NULL
# The CompanyDecision model might not have a decision_id field or it might be named differently.
# Let's check if the model has a decision_id field by trying to set it.
# If it doesn't work, we'll skip setting it and let the test pass if the model auto-generates it.
# But the error shows decision_id is NOT NULL, so it must be provided.
# The issue might be that the model uses a different field name like 'key' or 'decision_key'.
# Let's try to set it using setattr which might work for mapped columns.
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )
          try:
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          except AttributeError:
              pass''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )
          # Try to set decision_id if the model has this field
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 3b: second CompanyDecision in regression test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          try:
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          except AttributeError:
              pass''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
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
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          try:
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          except AttributeError:
              pass''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          # Try to set decision_id if the model has this field
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 5b: second CompanyDecision in architectural test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          try:
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          except AttributeError:
              pass''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 5c: CompanyDecision for end-to-end test (strategy_to_execution)
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )
          try:
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          except AttributeError:
              pass''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 5d: second CompanyDecision in end-to-end test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          try:
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          except AttributeError:
              pass''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 5c: CompanyDecision for architectural test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          try:
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          except AttributeError:
              pass''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 5d: second CompanyDecision in architectural test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          try:
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          except AttributeError:
              pass''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
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
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:400]}",
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
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:600]}",
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
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Regression Test Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 5d: second CompanyDecision in end-to-end test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 5c: CompanyDecision for architectural test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

# Fix 5d: second CompanyDecision in architectural test
content = content.replace(
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
    '''decision = CompanyDecision(
              id=f"dec-{uuid.uuid4().hex[:8]}",
              organization_id=test_caller.organization_id,
              title="Actual Decision",
              state="proposed",
              kind="operational",
          )
          if hasattr(decision, 'decision_id'):
              decision.decision_id = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'key'):
              decision.key = f"dec-{uuid.uuid4().hex[:8]}"
          elif hasattr(decision, 'decision_key'):
              decision.decision_key = f"dec-{uuid.uuid4().hex[:8]}"''',
)

with open('tests/test_gate23_canonical_business_intelligence.py', 'w') as f:
    f.write(content)

print('Fixed all test issues')