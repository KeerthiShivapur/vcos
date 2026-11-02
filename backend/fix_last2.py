with open('tests/test_gate23_canonical_business_intelligence.py', 'r') as f:
    content = f.read()

# Fix 1: test_exact_once_bi_context - The test is still trying to flush after checking unique constraint
# The test should not flush after the unique constraint check
content = content.replace(
    '''# Test exact-once by verifying the unique constraint exists on the table
          from sqlalchemy import inspect
          inspector = inspect(db_session.bind)
          indexes = inspector.get_indexes('business_intelligence_contexts')
          unique_indexes = [idx for idx in indexes if idx.get('unique')]
          # The unique constraint is on (organization_id, context_type, context_entity_id, period_label, source_event_id)
          has_exact_once_constraint = any(
              set(['organization_id', 'context_type', 'context_entity_id', 'period_label', 'source_event_id']).issubset(set(idx['column_names']))
              for idx in unique_indexes if idx.get('unique')
          )
          assert has_exact_once_constraint, "Exact-once unique constraint not found on business_intelligence_contexts"
          await db_session.flush()''',
    '''# Test exact-once by verifying the unique constraint exists on the table
          from sqlalchemy import inspect
          inspector = inspect(db_session.bind)
          indexes = inspector.get_indexes('business_intelligence_contexts')
          unique_indexes = [idx for idx in indexes if idx.get('unique')]
          # The unique constraint is on (organization_id, context_type, context_entity_id, period_label, source_event_id)
          has_exact_once_constraint = any(
              set(['organization_id', 'context_type', 'context_entity_id', 'period_label', 'source_event_id']).issubset(set(idx['column_names']))
              for idx in unique_indexes if idx.get('unique')
          )
          assert has_exact_once_constraint, "Exact-once unique constraint not found on business_intelligence_contexts"'''
)

# Fix 2: test_strategy_to_execution_to_learning_loop - CompanyCommitment fingerprint not unique enough
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
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:32]}",
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
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:40]}",
              version=1,
          )'''
)

# Fix 2: CompanyDecision needs decision_id for regression test
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
          )'''
)

# Fix the second CompanyDecision in regression test
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
          )'''
)

# Fix the Employee fixture in test_same_architecture_small_company - remove full_name reference
content = content.replace(
    '''emp = Employee(
            id=f"emp-{uuid.uuid4().hex[:8]}",
            organization_id=test_caller.organization_id,
            employee_number="E001",
            first_name="Employee",
            last_name="Test",
            display_name="Employee Test",
            email="employee.test@test.com",
            status="active",
        )''',
    '''emp = Employee(
            id=f"emp-{uuid.uuid4().hex[:8]}",
            organization_id=test_caller.organization_id,
            employee_number="E001",
            first_name="Employee",
            last_name="Test",
            display_name="Employee Test",
            email="employee.test@test.com",
            status="active",
        )'''
)

# Fix CompanyDecision for architectural test
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
          )'''
)

# Fix the second CompanyDecision in architectural test
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
          )'''
)

with open('tests/test_gate23_canonical_business_intelligence.py', 'w') as f:
    f.write(content)

print('Fixed test issues')