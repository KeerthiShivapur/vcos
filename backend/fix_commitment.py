with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix CompanyCommitment - change status to state and add commitment_type
old_comm = '''            comm1 = CompanyCommitment(
                organization_id=org.id,
                title="Platform Migration Commitment",
                description="Commit to completing platform migration by Q3",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )'''

new_comm = '''            comm1 = CompanyCommitment(
                organization_id=org.id,
                commitment_type="unconditional",
                title="Platform Migration Commitment",
                description="Commit to completing platform migration by Q3",
                state="proposed",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )'''

content = content.replace(old_comm, new_comm)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed CompanyCommitment')