with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

old = (
    b'            type_map = {\r\n'
    b'        "CompanyDecision": CompanyDecision,\r\n'
    b'        "CompanyAuthorization": CompanyAuthorization,\r\n'
    b'        "CompanyCommitment": CompanyCommitment,\r\n'
    b'        "CompanyAction": CompanyAction,\r\n'
    b'        "CompanyDecisionAlternative": CompanyDecisionAlternative,\r\n'
    b'        "CompanyDecisionContradiction": CompanyDecisionContradiction,\r\n'
    b'        "CompanyGoal": CompanyGoal,\r\n'
    b'        "CompanyObjective": CompanyObjective,\r\n'
    b'        "CompanyInitiative": CompanyInitiative,\r\n'
    b'        "CompanyIntent": CompanyIntent,\r\n'
    b'        "Project": Project,\r\n'
    b'        "Task": Task,\r\n'
    b'        "Employee": Employee,\r\n'
    b'    }\r\n'
    b'    model = type_map.get(entity_type)\r\n'
    b'        if not model:\r\n'
    b'            return None\r\n'
    b'        \r\n'
    b'        # For CompanyDecision, check by source_event_id instead of fingerprint'
)

new = (
    b'        type_map = {\r\n'
    b'            "CompanyDecision": CompanyDecision,\r\n'
    b'        "CompanyAuthorization": CompanyAuthorization,\r\n'
    b'        "CompanyCommitment": CompanyCommitment,\r\n'
    b'        "CompanyAction": CompanyAction,\r\n'
    b'        "CompanyDecisionAlternative": CompanyDecisionAlternative,\r\n'
    b'        "CompanyDecisionContradiction": CompanyDecisionContradiction,\r\n'
    b'        "CompanyGoal": CompanyGoal,\r\n'
    b'        "CompanyObjective": CompanyObjective,\r\n'
    b'        "CompanyInitiative": CompanyInitiative,\r\n'
    b'        "CompanyIntent": CompanyIntent,\r\n'
    b'        "Project": Project,\r\n'
    b'        "Task": Task,\r\n'
    b'        "Employee": Employee,\r\n'
    b'        }\r\n'
    b'        model = type_map.get(entity_type)\r\n'
    b'        if not model:\r\n'
    b'            return None\r\n'
    b'        \r\n'
    b'        # For CompanyDecision, check by source_event_id instead of fingerprint'
)

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')