with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix CompanyCommitment - change status to state
content = content.replace(
    '''            comm1 = CompanyCommitment(
                organization_id=org.id,
                commitment_type="unconditional",
                title="Complete Platform Migration",
                description="Complete platform migration to PostgreSQL 18",
                status="active",
                scope_type="objective",
                scope_id=obj1.id,
                authorization_id=auth1.id,
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )''',
    '''            comm1 = CompanyCommitment(
                organization_id=org.id,
                commitment_type="unconditional",
                title="Complete Platform Migration",
                description="Complete platform migration to PostgreSQL 18",
                state="proposed",
                scope_type="objective",
                scope_id=obj1.id,
                authorization_id=auth1.id,
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed CompanyCommitment status -> state')