with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the specific block at lines 1810-1837
old = (
    b'            # Execute the actual mutation\r\n'
    b'            if mutation_fn:\r\n'
    b'                # For UPDATE mutations, use database-level optimistic concurrency\r\n'
    b'                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:\r\n'
    b'                    # Load the model for the entity type\r\n'
    b'            type_map = {\r\n'
    b'                    "CompanyDecision": CompanyDecision,\r\n'
    b'                    "CompanyAuthorization": CompanyAuthorization,\r\n'
    b'                    "CompanyCommitment": CompanyCommitment,\r\n'
    b'                    "CompanyAction": CompanyAction,\r\n'
    b'                    "CompanyDecisionAlternative": CompanyDecisionAlternative,\r\n'
    b'                    "CompanyDecisionContradiction": CompanyDecisionContradiction,\r\n'
    b'                    "CompanyGoal": CompanyGoal,\r\n'
    b'                    "CompanyObjective": CompanyObjective,\r\n'
    b'                    "CompanyInitiative": CompanyInitiative,\r\n'
    b'                    "CompanyIntent": CompanyIntent,\r\n'
    b'                    "Project": Project,\r\n'
    b'                    "Task": Task,\r\n'
    b'                    "Employee": Employee,\r\n'
    b'                    "User": User,\r\n'
    b'                        "Organization": Organization,\r\n'
    b'                    }\r\n'
    b'                    model = type_map.get(target_entity_type)\r\n'
    b'                    if model:\r\n'
    b'                        # Use database-level optimistic update\r\n'
    b'                        pass\r\n'
    b'                \r\n'
    b'                result = await mutation_fn(db)'
)

new = (
    b'            # Execute the actual mutation\r\n'
    b'            if mutation_fn:\r\n'
    b'                # For UPDATE mutations, use database-level optimistic concurrency\r\n'
    b'                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:\r\n'
    b'                    # Load the model for the entity type\r\n'
    b'                    type_map = {\r\n'
    b'                        "CompanyDecision": CompanyDecision,\r\n'
    b'                        "CompanyAuthorization": CompanyAuthorization,\r\n'
    b'                        "CompanyCommitment": CompanyCommitment,\r\n'
    b'                        "CompanyAction": CompanyAction,\r\n'
    b'                        "CompanyDecisionAlternative": CompanyDecisionAlternative,\r\n'
    b'                        "CompanyDecisionContradiction": CompanyDecisionContradiction,\r\n'
    b'                        "CompanyGoal": CompanyGoal,\r\n'
    b'                        "CompanyObjective": CompanyObjective,\r\n'
    b'                        "CompanyInitiative": CompanyInitiative,\r\n'
    b'                        "CompanyIntent": CompanyIntent,\r\n'
    b'                        "Project": Project,\r\n'
    b'                        "Task": Task,\r\n'
    b'                        "Employee": Employee,\r\n'
    b'                        "User": User,\r\n'
    b'                        "Organization": Organization,\r\n'
    b'                    }\r\n'
    b'                    model = type_map.get(target_entity_type)\r\n'
    b'                    if model:\r\n'
    b'                        # Use database-level optimistic update\r\n'
    b'                        pass\r\n'
    b'                \r\n'
    b'                result = await mutation_fn(db)'
)

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')