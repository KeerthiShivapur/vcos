with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

old = (
    b'if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:\n'
    b'                    # Load the model for the entity type\n'
    b'                type_map = {\n'
    b'                    "CompanyDecision": CompanyDecision,\n'
    b'                    "CompanyAuthorization": CompanyAuthorization,\n'
    b'                    "CompanyCommitment": CompanyCommitment,\n'
    b'                    "CompanyAction": CompanyAction,\n'
    b'                    "CompanyDecisionAlternative": CompanyDecisionAlternative,\n'
    b'                    "CompanyDecisionContradiction": CompanyDecisionContradiction,\n'
    b'                    "CompanyGoal": CompanyGoal,\n'
    b'                    "CompanyObjective": CompanyObjective,\n'
    b'                    "CompanyInitiative": CompanyInitiative,\n'
    b'                    "CompanyIntent": CompanyIntent,\n'
    b'                    "Project": Project,\n'
    b'                    "Task": Task,\n'
    b'                    "Employee": Employee,\n'
    b'                "User": User,\n'
    b'                        "Organization": Organization,\n'
    b'                    }\n'
    b'                    model = type_map.get(target_entity_type)\n'
    b'                    if model:\n'
    b'                        # Use database-level optimistic update\n'
    b'                        pass\n'
    b'                result = await mutation_fn(db)'
)

new = (
    b'if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:\n'
    b'                    # Load the model for the entity type\n'
    b'                    type_map = {\n'
    b'                        "CompanyDecision": CompanyDecision,\n'
    b'                        "CompanyAuthorization": CompanyAuthorization,\n'
    b'                        "CompanyCommitment": CompanyCommitment,\n'
    b'                        "CompanyAction": CompanyAction,\n'
    b'                        "CompanyDecisionAlternative": CompanyDecisionAlternative,\n'
    b'                        "CompanyDecisionContradiction": CompanyDecisionContradiction,\n'
    b'                        "CompanyGoal": CompanyGoal,\n'
    b'                        "CompanyObjective": CompanyObjective,\n'
    b'                        "CompanyInitiative": CompanyInitiative,\n'
    b'                        "CompanyIntent": CompanyIntent,\n'
    b'                        "Project": Project,\n'
    b'                        "Task": Task,\n'
    b'                        "Employee": Employee,\n'
    b'                        "User": User,\n'
    b'                        "Organization": Organization,\n'
    b'                    }\n'
    b'                    model = type_map.get(target_entity_type)\n'
    b'                    if model:\n'
    b'                        # Use database-level optimistic update\n'
    b'                        pass\n'
    b'                result = await mutation_fn(db)'
)

if old in content:
    content = content.replace(old, new)
    with open('app/intelligence/canonical_mutation.py', 'wb') as f:
        f.write(content)
    print('Fixed')
else:
    print('Pattern not found')
    # Try to find what's different
    import re
    pattern = rb'if mutation_type == MutationType\.UPDATE.*?result = await mutation_fn\(db\)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        print('Found:', repr(match.group()[:500]))