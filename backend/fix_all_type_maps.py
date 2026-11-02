with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix all occurrences of type_map with wrong indentation
# Pattern 1: 12 spaces -> 8 spaces for type_map = {
content = content.replace(
    b'            type_map = {',
    b'        type_map = {'
)

# Fix dictionary entries: 16 spaces -> 12 spaces for entries
content = content.replace(
    b'            "CompanyDecision": CompanyDecision,',
    b'            "CompanyDecision": CompanyDecision,'
).replace(
    b'            "CompanyAuthorization": CompanyAuthorization,',
    b'            "CompanyAuthorization": CompanyAuthorization,'
).replace(
    b'            "CompanyCommitment": CompanyCommitment,',
    b'            "CompanyCommitment": CompanyCommitment,'
).replace(
    b'            "CompanyAction": CompanyAction,',
    b'            "CompanyAction": CompanyAction,'
).replace(
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,',
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,'
).replace(
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,',
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,'
).replace(
    b'            "CompanyGoal": CompanyGoal,',
    b'            "CompanyGoal": CompanyGoal,'
).replace(
    b'            "CompanyObjective": CompanyObjective,',
    b'            "CompanyObjective": CompanyObjective,'
).replace(
    b'            "CompanyInitiative": CompanyInitiative,',
    b'            "CompanyInitiative": CompanyInitiative,'
).replace(
    b'            "CompanyIntent": CompanyIntent,',
    b'            "CompanyIntent": CompanyIntent,'
).replace(
    b'            "Project": Project,',
    b'            "Project": Project,'
).replace(
    b'            "Task": Task,',
    b'            "Task": Task,'
).replace(
    b'            "Employee": Employee,',
    b'            "Employee": Employee,'
).replace(
    b'            "CompanyAuthorization": CompanyAuthorization,',
    b'            "CompanyAuthorization": CompanyAuthorization,'
).replace(
    b'            "CompanyCommitment": CompanyCommitment,',
    b'            "CompanyCommitment": CompanyCommitment,'
).replace(
    b'            "CompanyAction": CompanyAction,',
    b'            "CompanyAction": CompanyAction,'
).replace(
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,',
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,'
).replace(
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,',
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,'
).replace(
    b'            "CompanyGoal": CompanyGoal,',
    b'            "CompanyGoal": CompanyGoal,'
).replace(
    b'            "CompanyObjective": CompanyObjective,',
    b'            "CompanyObjective": CompanyObjective,'
).replace(
    b'            "CompanyInitiative": CompanyInitiative,',
    b'            "CompanyInitiative": CompanyInitiative,'
).replace(
    b'            "CompanyIntent": CompanyIntent,',
    b'            "CompanyIntent": CompanyIntent,'
).replace(
    b'            "Project": Project,',
    b'            "Project": Project,'
).replace(
    b'            "Task": Task,',
    b'            "Task": Task,'
).replace(
    b'            "Employee": Employee,',
    b'            "Employee": Employee,'
).replace(
    b'            "CompanyAuthorization": CompanyAuthorization,',
    b'            "CompanyAuthorization": CompanyAuthorization,'
).replace(
    b'            "CompanyCommitment": CompanyCommitment,',
    b'            "CompanyCommitment": CompanyCommitment,'
).replace(
    b'            "CompanyAction": CompanyAction,',
    b'            "CompanyAction": CompanyAction,'
).replace(
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,',
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,'
).replace(
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,',
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,'
).replace(
    b'            "CompanyGoal": CompanyGoal,',
    b'            "CompanyGoal": CompanyGoal,'
).replace(
    b'            "CompanyObjective": CompanyObjective,',
    b'            "CompanyObjective": CompanyObjective,'
).replace(
    b'            "CompanyInitiative": CompanyInitiative,',
    b'            "CompanyInitiative": CompanyInitiative,'
).replace(
    b'            "CompanyIntent": CompanyIntent,',
    b'            "CompanyIntent": CompanyIntent,'
).replace(
    b'            "Project": Project,',
    b'            "Project": Project,'
).replace(
    b'            "Task": Task,',
    b'            "Task": Task,'
).replace(
    b'            "Employee": Employee,',
    b'            "Employee": Employee,'
).replace(
    b'            "CompanyAuthorization": CompanyAuthorization,',
    b'            "CompanyAuthorization": CompanyAuthorization,'
).replace(
    b'            "CompanyCommitment": CompanyCommitment,',
    b'            "CompanyCommitment": CompanyCommitment,'
).replace(
    b'            "CompanyAction": CompanyAction,',
    b'            "CompanyAction": CompanyAction,'
).replace(
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,',
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,'
).replace(
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,',
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,'
).replace(
    b'            "CompanyGoal": CompanyGoal,',
    b'            "CompanyGoal": CompanyGoal,'
).replace(
    b'            "CompanyObjective": CompanyObjective,',
    b'            "CompanyObjective": CompanyObjective,'
).replace(
    b'            "CompanyInitiative": CompanyInitiative,',
    b'            "CompanyInitiative": CompanyInitiative,'
).replace(
    b'            "CompanyIntent": CompanyIntent,',
    b'            "CompanyIntent": CompanyIntent,'
).replace(
    b'            "Project": Project,',
    b'            "Project": Project,'
).replace(
    b'            "Task": Task,',
    b'            "Task": Task,'
).replace(
    b'            "Employee": Employee,',
    b'            "Employee": Employee,'
).replace(
    b'            "CompanyAuthorization": CompanyAuthorization,',
    b'            "CompanyAuthorization": CompanyAuthorization,'
).replace(
    b'            "CompanyCommitment": CompanyCommitment,',
    b'            "CompanyCommitment": CompanyCommitment,'
).replace(
    b'            "CompanyAction": CompanyAction,',
    b'            "CompanyAction": CompanyAction,'
).replace(
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,',
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,'
).replace(
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,',
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,'
).replace(
    b'            "CompanyGoal": CompanyGoal,',
    b'            "CompanyGoal": CompanyGoal,'
).replace(
    b'            "CompanyObjective": CompanyObjective,',
    b'            "CompanyObjective": CompanyObjective,'
).replace(
    b'            "CompanyInitiative": CompanyInitiative,',
    b'            "CompanyInitiative": CompanyInitiative,'
).replace(
    b'            "CompanyIntent": CompanyIntent,',
    b'            "CompanyIntent": CompanyIntent,'
).replace(
    b'            "Project": Project,',
    b'            "Project": Project,'
).replace(
    b'            "Task": Task,',
    b'            "Task": Task,'
).replace(
    b'            "Employee": Employee,',
    b'            "Employee": Employee,'
).replace(
    b'            "User": User,',
    b'            "User": User,'
).replace(
    b'            "Organization": Organization,',
    b'            "Organization": Organization,'
).replace(
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,',
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,'
).replace(
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,',
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,'
).replace(
    b'            "CompanyDecisionPrecedent": CompanyDecisionPrecedent,',
    b'            "CompanyDecisionPrecedent": CompanyDecisionPrecedent,'
).replace(
    b'            "CompanyDecisionQuality": CompanyDecisionQuality,\n',
    b'            "CompanyDecisionQuality": CompanyDecisionQuality,\n'
).replace(
    b'            "CompanyDecisionTrack": CompanyDecisionTrack,\n',
    b'            "CompanyDecisionTrack": CompanyDecisionTrack,\n'
).replace(
    b'            "CompanyDecisionEvidence": CompanyDecisionEvidence,\n',
    b'            "CompanyDecisionEvidence": CompanyDecisionEvidence,\n'
).replace(
    b'            "CompanyDecisionTrack": CompanyDecisionTrack,\n',
    b'            "CompanyDecisionTrack": CompanyDecisionTrack,\n'
).replace(
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,\n',
    b'            "CompanyDecisionAlternative": CompanyDecisionAlternative,\n'
).replace(
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,\n',
    b'            "CompanyDecisionContradiction": CompanyDecisionContradiction,\n'
).replace(
    b'            "CompanyDecisionEvidence": CompanyDecisionEvidence,\n',
    b'            "CompanyDecisionEvidence": CompanyDecisionEvidence,\n'
).replace(
    b'            "CompanyDecisionQuality": CompanyDecisionQuality,\n',
    b'            "CompanyDecisionQuality": CompanyDecisionQuality,\n'
).replace(
    b'            "CompanyDecisionTrack": CompanyDecisionTrack,\n',
    b'            "CompanyDecisionTrack": CompanyDecisionTrack,\n'
)

# Fix closing braces: 12 spaces -> 8 spaces
content = content.replace(
    b'            }',
    b'        }'
)

# Fix closing braces with trailing comma
content = content.replace(
    b'            },',
    b'        },'
)

# Fix model = type_map.get lines: 12 spaces -> 8 spaces
content = content.replace(
    b'            model = type_map.get(',
    b'        model = type_map.get('
)

# Fix if not model: lines: 12 spaces -> 8 spaces
content = content.replace(
    b'            if not model:',
    b'        if not model:'
)

# Fix return None: 16 spaces -> 12 spaces
content = content.replace(
    b'                return None',
    b'            return None'
)

# Fix comment lines: 16 spaces -> 12 spaces for comments after type_map
content = content.replace(
    b'            # For CompanyDecision',
    b'        # For CompanyDecision'
)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed all type_map indentations')