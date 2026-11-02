with open('tests/acceptance/test_backup_restore_roundtrip.py', 'r') as f:
    content = f.read()

# Add the missing import for ApprovalPolicy
content = content.replace(
    'from app.models.execution_strategy import (\n    CompanyCommitment, CompanyAuthorization, CompanyObjective, CompanyGoal,\n    CompanyInitiative, ObjectiveOutcome, ObjectiveOutcomeAssessment\n)',
    '''from app.models.execution_strategy import (
    CompanyCommitment, CompanyAuthorization, CompanyObjective, CompanyGoal,
    CompanyInitiative, ObjectiveOutcome, ObjectiveOutcomeAssessment
)
from app.models.governance import ApprovalPolicy''')

with open('tests/acceptance/test_backup_restore_roundtrip.py', 'w') as f:
    f.write(content)

print('Added ApprovalPolicy import')