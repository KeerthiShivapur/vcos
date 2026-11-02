with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

old = (
    b'    async def _load_entity(self, db: AsyncSession, entity_type: str, entity_id: str):\r\n'
    b'        """Load entity by type and ID."""\r\n'
    b'    type_map = {\r\n'
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
    b'        "CanonicalOperation": CanonicalOperation,\r\n'
    b'        }\r\n'
    b'        model = type_map.get(entity_type)\r\n'
    b'        if not model:\r\n'
    b'            return None\r\n'
    b'        return await db.get(model, entity_id)'
)

new = (
    b'    async def _load_entity(self, db: AsyncSession, entity_type: str, entity_id: str):\r\n'
    b'        """Load entity by type and ID."""\r\n'
    b'        type_map = {\r\n'
    b'            "CompanyDecision": CompanyDecision,\r\n'
    b'        "CompanyAuthorization": CompanyAuthorization,\r\n'
    b'            "CompanyCommitment": CompanyCommitment,\r\n'
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
    b'        "CanonicalOperation": CanonicalOperation,\r\n'
    b'        }\r\n'
    b'        model = type_map.get(entity_type)\r\n'
    b'        if not model:\r\n'
    b'            return None\r\n'
    b'        return await db.get(model, entity_id)'
)

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')