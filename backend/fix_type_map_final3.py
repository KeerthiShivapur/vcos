with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

old = (
    b'            type_map = {\n'
    b'                "CompanyDecision": CompanyDecision,\n'
    b'        "CompanyAuthorization": CompanyAuthorization,\n'
    b'        "CompanyCommitment": CompanyCommitment,\n'
    b'        "CompanyAction": CompanyAction,\n'
    b'        "CompanyDecisionAlternative": CompanyDecisionAlternative,\n'
    b'        "CompanyDecisionContradiction": CompanyDecisionContradiction,\n'
    b'        "CompanyGoal": CompanyGoal,\n'
    b'        "CompanyObjective": CompanyObjective,\n'
    b'        "CompanyInitiative": CompanyInitiative,\n'
    b'        "CompanyIntent": CompanyIntent,\n'
    b'        "Project": Project,\n'
    b'        "Task": Task,\n'
    b'        "Employee": Employee,\n'
    b'    }\n'
    b'    model = type_map.get(entity_type)\n'
    b'        if not model:\n'
    b'            return None\n'
    b'        \n'
    b'        # For CompanyDecision, check by source_event_id instead of fingerprint'
)

new = (
    b'        type_map = {\n'
    b'            "CompanyDecision": CompanyDecision,\n'
    b'        "CompanyAuthorization": CompanyAuthorization,\n'
    b'        "CompanyCommitment": CompanyCommitment,\n'
    b'        "CompanyAction": CompanyAction,\n'
    b'        "CompanyDecisionAlternative": CompanyDecisionAlternative,\n'
    b'        "CompanyDecisionContradiction": CompanyDecisionContradiction,\n'
    b'        "CompanyGoal": CompanyGoal,\n'
    b'        "CompanyObjective": CompanyObjective,\n'
    b'        "CompanyInitiative": CompanyInitiative,\n'
    b'        "CompanyIntent": CompanyIntent,\n'
    b'        "Project": Project,\n'
    b'        "Task": Task,\n'
    b'        "Employee": Employee,\n'
    b'        }\n'
    b'        model = type_map.get(entity_type)\n'
    b'        if not model:\n'
    b'            return None\n'
    b'        \n'
    b'        # For CompanyDecision, check by source_event_id instead of fingerprint'
)

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')