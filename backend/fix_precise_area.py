with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the specific area at index 79648
old = b'type_map = {\n                        "CompanyDecision": CompanyDecision,\n                        "CompanyAuthorization": CompanyAuthorization,\n                        "CompanyCommitment": CompanyCommitment,\n                        "CompanyAction": CompanyAction,\n                        "CompanyDecisionAlternative": CompanyDecisionAlternative,\n                        "CompanyDecisionContradiction": CompanyDecisionContradiction,\n                        "CompanyGoal": CompanyGoal,\n                        "CompanyObjective": CompanyObjective,\r\n                        "CompanyInitiative": CompanyInitiative,\r\n                        "CompanyIntent": CompanyIntent,\r\n                        "Project": Project,\r\n                        "Task": Task,\r\n                        "Employee": Employee,\r\n                        "User": User,\r\n                        "Organization": Organization,\r\n                    }\r\n                    model = type_map.get(target_entity_type)\r\n                    if model:\r\n                        # Use database-level optimistic update\r\n                        pass\r\n                '

new = b'type_map = {\n                "CompanyDecision": CompanyDecision,\n                "CompanyAuthorization": CompanyAuthorization,\n                "CompanyCommitment": CompanyCommitment,\n                "CompanyAction": CompanyAction,\n                "CompanyDecisionAlternative": CompanyDecisionAlternative,\n                "CompanyDecisionContradiction": CompanyDecisionContradiction,\n                "CompanyGoal": CompanyGoal,\n                "CompanyObjective": CompanyObjective,\n                "CompanyInitiative": CompanyInitiative,\n                "CompanyIntent": CompanyIntent,\n                "Project": Project,\n                "Task": Task,\n                "Employee": Employee,\n            }\n            model = type_map.get(target_entity_type)\n            if model:\n                # Use database-level optimistic update\n                pass\n            '

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')