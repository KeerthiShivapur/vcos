with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

old = b'            type_map = {\r\n        "CompanyDecision": CompanyDecision,\r\n        "CompanyAuthorization": CompanyAuthorization,\r\n        "CompanyCommitment": CompanyCommitment,\r\n        "CompanyAction": CompanyAction,\r\n        "CompanyDecisionAlternative": CompanyDecisionAlternative,\r\n        "CompanyDecisionContradiction": CompanyDecisionContradiction,\r\n        "CompanyGoal": CompanyGoal,\r\n        "CompanyObjective": CompanyObjective,\r\n        "CompanyInitiative": CompanyInitiative,\r\n        "CompanyIntent": CompanyIntent,\r\n        "Project": Project,\r\n        "Task": Task,\r\n        "Employee": Employee,\r\n    }\r\n    model = type_map.get(entity_type)\r\n        if not model:\r\n        return None\r\n        \r\n        # For CompanyDecision, check by source_event_id instead of fingerprint'

new = b'        type_map = {\r\n            "CompanyDecision": CompanyDecision,\r\n        "CompanyAuthorization": CompanyAuthorization,\r\n        "CompanyCommitment": CompanyCommitment,\r\n        "CompanyAction": CompanyAction,\r\n        "CompanyDecisionAlternative": CompanyDecisionAlternative,\r\n        "CompanyDecisionContradiction": CompanyDecisionContradiction,\r\n        "CompanyGoal": CompanyGoal,\r\n        "CompanyObjective": CompanyObjective,\r\n        "CompanyInitiative": CompanyInitiative,\r\n        "CompanyIntent": CompanyIntent,\r\n        "Project": Project,\r\n        "Task": Task,\r\n        "Employee": Employee,\r\n        }\r\n        model = type_map.get(entity_type)\r\n        if not model:\r\n            return None\r\n        \r\n        # For CompanyDecision, check by source_event_id instead of fingerprint'

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')