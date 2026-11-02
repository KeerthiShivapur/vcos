with open('tests/test_gate23_canonical_business_intelligence.py', 'r') as f:
    content = f.read()

# Fix 1: test_same_architecture_small_company - Employee.full_name issue
# The Employee model uses first_name/last_name, not full_name
content = content.replace(
    '''            emp = Employee(
                id=f"emp-small-{i}-{uuid.uuid4().hex[:8]}",
                organization_id=test_caller.organization_id,
                employee_number=f"E00{i}",
                full_name=f"Employee {i}",
                status="active",
            )''',
    '''            emp = Employee(
                id=f"emp-small-{i}-{uuid.uuid4().hex[:8]}",
                organization_id=test_caller.organization_id,
                employee_number=f"E00{i}",
                first_name=f"Employee",
                last_name=f"{i}",
                display_name=f"Employee {i}",
                status="active",
            )''',
)

# Fix 2: test_company_decision_still_works - CompanyDecision.decision_id NOT NULL
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

# Fix 2b: second CompanyDecision in regression test
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

# Fix 3: test_decision_not_authorization_not_commitment - CompanyDecision.decision_id NOT NULL
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

# Fix 4: test_strategy_to_execution_to_learning_loop - CompanyCommitment fingerprint NOT NULL
# The fingerprint needs to be unique enough
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
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:64]}",
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
              fingerprint=f"comm-fp-{uuid.uuid4().hex[:80]}",
              version=1,
          )''',
)

# Fix 5: test_strategy_to_execution_to_learning_loop - CompanyDecision.decision_id NOT NULL
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

# Fix 5b: second CompanyDecision in end-to-end test
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