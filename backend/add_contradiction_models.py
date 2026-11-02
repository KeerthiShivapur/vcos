with open('app/intelligence/company_context.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add contradiction models to the model_map in resolve_accessible_ids
old = '''        model_map = {
            "project": Project, "task": Task, "decision": CompanyDecision,
            "conversation": Conversation, "message": Message,
            "scope": GovernanceScope, "approval_policy": ApprovalPolicy,
            "goal": CompanyGoal, "budget": Budget, "employee": Employee,
            "commitment": CompanyCommitment,
            "authorization": CompanyAuthorization,
            "action": CompanyAction,
        }'''

new = '''        model_map = {
            "project": Project, "task": Task, "decision": CompanyDecision,
            "conversation": Conversation, "message": Message,
            "scope": GovernanceScope, "approval_policy": ApprovalPolicy,
            "goal": CompanyGoal, "budget": Budget, "employee": Employee,
            "commitment": CompanyCommitment,
            "authorization": CompanyAuthorization,
            "action": CompanyAction,
            # Contradiction kinds for Gate 6-E
            "decision_contradiction": CompanyDecisionContradiction,
            "objective_contradiction": ObjectiveContradiction,
        }'''

content = content.replace(old, new)

with open('app/intelligence/company_context.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added contradiction models to model_map')