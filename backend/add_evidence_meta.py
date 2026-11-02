with open('app/intelligence/company_context.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add contradiction kinds to _EVIDENCE_META
old = '''_EVIDENCE_META: dict[str, dict[str, Any]] = {
    "project": {"source": "projects", "url": "/projects/{}"},
    "task": {"source": "tasks", "url": "/tasks/{}"},
    "decision": {"source": "decisions", "url": "/decisions/{}"},
    "conversation": {"source": "conversations", "url": "/messaging/{}"},
    "message": {"source": "messages", "url": "/messaging/messages/{}"},
    "scope": {"source": "governance_scopes", "url": "/governance/scopes/{}"},
    "approval_policy": {"source": "approval_policies", "url": "/governance/approval-policies/{}"},
    "goal": {"source": "goals", "url": "/goals/{}"},
    "budget": {"source": "budgets", "url": "/finance/budgets/{}"},
    "employee": {"source": "employees", "url": "/people/{}"},
    "commitment": {"source": "commitments", "url": "/commitments/{}"},
    "authorization": {"source": "authorizations", "url": "/authorizations/{}"},
    "action": {"source": "actions", "url": "/actions/{}"},
    # Slice 4D.2 � knowledge evidence (urls follow the knowledge entity routes)
    "document": {"source": "documents", "url": "/documents/{}"},
    "wiki": {"source": "wiki_pages", "url": "/wiki/{}"},
    "policy": {"source": "policies", "url": "/policies/{}"},
    "sop": {"source": "sops", "url": "/sops/{}"},
    "template": {"source": "templates", "url": "/templates/{}"},
}'''

new = '''_EVIDENCE_META: dict[str, dict[str, Any]] = {
    "project": {"source": "projects", "url": "/projects/{}"},
    "task": {"source": "tasks", "url": "/tasks/{}"},
    "decision": {"source": "decisions", "url": "/decisions/{}"},
    "conversation": {"source": "conversations", "url": "/messaging/{}"},
    "message": {"source": "messages", "url": "/messaging/messages/{}"},
    "scope": {"source": "governance_scopes", "url": "/governance/scopes/{}"},
    "approval_policy": {"source": "approval_policies", "url": "/governance/approval-policies/{}"},
    "goal": {"source": "goals", "url": "/goals/{}"},
    "budget": {"source": "budgets", "url": "/finance/budgets/{}"},
    "employee": {"source": "employees", "url": "/people/{}"},
    "commitment": {"source": "commitments", "url": "/commitments/{}"},
    "authorization": {"source": "authorizations", "url": "/authorizations/{}"},
    "action": {"source": "actions", "url": "/actions/{}"},
    # Contradiction kinds for Gate 6-E
    "decision_contradiction": {"source": "company_decision_contradictions", "url": "/contradictions/decision/{}"},
    "objective_contradiction": {"source": "objective_contradictions", "url": "/contradictions/objective/{}"},
    # Slice 4D.2 � knowledge evidence (urls follow the knowledge entity routes)
    "document": {"source": "documents", "url": "/documents/{}"},
    "wiki": {"source": "wiki_pages", "url": "/wiki/{}"},
    "policy": {"source": "policies", "url": "/policies/{}"},
    "sop": {"source": "sops", "url": "/sops/{}"},
    "template": {"source": "templates", "url": "/templates/{}"},
}'''

content = content.replace(old, new)

with open('app/intelligence/company_context.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added contradiction kinds to _EVIDENCE_META')